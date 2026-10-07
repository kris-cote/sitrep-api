import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]


class DatabaseReadinessTests(unittest.TestCase):
    def setUp(self):
        sqlalchemy = types.ModuleType('sqlalchemy')
        sqlalchemy.create_engine = MagicMock()
        sqlalchemy.text = lambda value: value
        pool = types.ModuleType('sqlalchemy.pool')
        pool.NullPool = object()
        url_module = types.ModuleType('app.core.database_url')
        url_module.sync_database_url = lambda: 'postgresql://fixture.invalid/test'
        self.modules = patch.dict(sys.modules, {
            'sqlalchemy': sqlalchemy, 'sqlalchemy.pool': pool,
            'app.core.database_url': url_module,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location('probe', ROOT / 'app/core/database_health.py')
        self.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.probe)
        self.engine = MagicMock()
        self.connection = self.engine.begin.return_value.__enter__.return_value
        self.connection.dialect.name = 'postgresql'
        self.connection.execute.return_value.scalar_one.return_value = 1
        self.probe.create_engine.return_value = self.engine

    def test_success_queries_database_and_closes_engine(self):
        self.assertTrue(self.probe.database_ready())
        self.assertEqual([c.args[0] for c in self.connection.execute.call_args_list],
                         ['SET LOCAL statement_timeout = 2000', 'SELECT 1'])
        self.engine.dispose.assert_called_once()

    def test_postgres_connection_timeout_is_bounded(self):
        self.probe.database_ready()
        self.assertEqual(self.probe.create_engine.call_args.kwargs['connect_args'], {'connect_timeout': 2})

    def test_connection_failure_is_unready(self):
        self.engine.begin.side_effect = RuntimeError('credential-bearing provider failure')
        self.assertFalse(self.probe.database_ready())
        self.engine.dispose.assert_called_once()

    def test_query_failure_is_unready(self):
        self.connection.execute.side_effect = RuntimeError('query failed')
        self.assertFalse(self.probe.database_ready())

    def test_missing_configuration_is_unready(self):
        self.probe.sync_database_url = MagicMock(side_effect=RuntimeError('missing configuration'))
        self.assertFalse(self.probe.database_ready())
        self.probe.create_engine.assert_not_called()

    def test_unexpected_query_result_is_unready(self):
        self.connection.execute.return_value.scalar_one.return_value = 0
        self.assertFalse(self.probe.database_ready())

    def route(self, ready):
        tree = ast.parse((ROOT / 'app/api/routers/core.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'readyz')
        node.decorator_list = []
        namespace = {'database_ready': lambda: ready,
                     'JSONResponse': lambda **kw: kw}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<readyz>', 'exec'), namespace)
        return namespace['readyz']()

    def test_ready_route_has_explicit_database_evidence(self):
        response = self.route(True)
        self.assertEqual(response['status_code'], 200)
        self.assertEqual(response['content']['database'], 'connected')
        self.assertEqual(response['headers']['Cache-Control'], 'no-store')

    def test_unready_route_returns_503_without_exception_details(self):
        response = self.route(False)
        self.assertEqual(response['status_code'], 503)
        self.assertEqual(response['content'], {'ok': False, 'status': 'unavailable', 'database': 'unavailable'})


if __name__ == '__main__':
    unittest.main()
