"""Self-balancing AVL tree for BountyBook job 1063de95-75f4-4170-8879-f5b1b683bb9b."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Node:
    key: int
    left: _Node | None = None
    right: _Node | None = None
    height: int = 1


class AVLTree:
    """A set-like AVL tree with logarithmic insert, delete and search."""

    def __init__(self) -> None:
        self._root: _Node | None = None

    @staticmethod
    def _height(node: _Node | None) -> int:
        return node.height if node is not None else 0

    @classmethod
    def _refresh(cls, node: _Node) -> None:
        node.height = 1 + max(cls._height(node.left), cls._height(node.right))

    @classmethod
    def _rotate_left(cls, node: _Node) -> _Node:
        pivot = node.right
        if pivot is None:  # defensive invariant guard
            return node
        node.right = pivot.left
        pivot.left = node
        cls._refresh(node)
        cls._refresh(pivot)
        return pivot

    @classmethod
    def _rotate_right(cls, node: _Node) -> _Node:
        pivot = node.left
        if pivot is None:  # defensive invariant guard
            return node
        node.left = pivot.right
        pivot.right = node
        cls._refresh(node)
        cls._refresh(pivot)
        return pivot

    @classmethod
    def _rebalance(cls, node: _Node) -> _Node:
        cls._refresh(node)
        balance = cls._height(node.left) - cls._height(node.right)
        if balance > 1:
            if node.left is not None and cls._height(node.left.left) < cls._height(node.left.right):
                node.left = cls._rotate_left(node.left)
            return cls._rotate_right(node)
        if balance < -1:
            if node.right is not None and cls._height(node.right.right) < cls._height(node.right.left):
                node.right = cls._rotate_right(node.right)
            return cls._rotate_left(node)
        return node

    @classmethod
    def _insert(cls, node: _Node | None, key: int) -> _Node:
        if node is None:
            return _Node(key)
        if key < node.key:
            node.left = cls._insert(node.left, key)
        elif key > node.key:
            node.right = cls._insert(node.right, key)
        else:
            return node
        return cls._rebalance(node)

    def insert(self, key: int) -> None:
        self._root = self._insert(self._root, key)

    @staticmethod
    def _minimum(node: _Node) -> _Node:
        while node.left is not None:
            node = node.left
        return node

    @classmethod
    def _delete(cls, node: _Node | None, key: int) -> _Node | None:
        if node is None:
            return None
        if key < node.key:
            node.left = cls._delete(node.left, key)
        elif key > node.key:
            node.right = cls._delete(node.right, key)
        elif node.left is None:
            return node.right
        elif node.right is None:
            return node.left
        else:
            successor = cls._minimum(node.right)
            node.key = successor.key
            node.right = cls._delete(node.right, successor.key)
        return cls._rebalance(node)

    def delete(self, key: int) -> None:
        self._root = self._delete(self._root, key)

    def search(self, key: int) -> bool:
        node = self._root
        while node is not None:
            if key == node.key:
                return True
            node = node.left if key < node.key else node.right
        return False

    def inorder(self) -> list[int]:
        result: list[int] = []
        stack: list[_Node] = []
        node = self._root
        while node is not None or stack:
            while node is not None:
                stack.append(node)
                node = node.left
            node = stack.pop()
            result.append(node.key)
            node = node.right
        return result

    def height(self) -> int:
        return self._height(self._root)


def _acceptance_tests() -> None:
    import math

    tree = AVLTree()
    for value in [30, 20, 40, 10, 25, 35, 50]:
        tree.insert(value)
    assert tree.inorder() == [10, 20, 25, 30, 35, 40, 50]
    assert tree.height() <= math.ceil(math.log2(7 + 1)) + 1, "Tree not balanced"
    assert tree.search(25) is True
    assert tree.search(99) is False
    tree.delete(20)
    assert tree.inorder() == [10, 25, 30, 35, 40, 50]
    assert tree.search(20) is False

    right_left = AVLTree()
    for value in [10, 30, 20]:
        right_left.insert(value)
    assert right_left.inorder() == [10, 20, 30]
    assert right_left.height() == 2
    print("All tests passed")


if __name__ == "__main__":
    _acceptance_tests()
