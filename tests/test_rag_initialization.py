import ast
from pathlib import Path
import unittest


class RagInitializationTests(unittest.TestCase):
    def test_rag_tool_is_not_constructed_during_module_import(self):
        source = Path("src/utils/rag_utils.py").read_text()
        tree = ast.parse(source)

        eager_rag_assignments = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "rag_tool"
                for target in node.targets
            )
        ]

        self.assertEqual(eager_rag_assignments, [])


if __name__ == "__main__":
    unittest.main()
