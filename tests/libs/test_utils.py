import pytest
from eth_utils import keccak

from raiden_libs.utils import (
    compute_merkle_proof,
    compute_merkle_tree,
    get_merkle_root,
    is_empty_merkle_root,
    validate_merkle_proof,
)


def test_compute_merkle_tree_invalid_length():
    with pytest.raises(ValueError):
        compute_merkle_tree([b'not32bytes', b'neither'])

    with pytest.raises(ValueError):
        compute_merkle_tree([b''])


def test_compute_merkle_tree_duplicated():
    hash_0 = keccak(b'x')
    hash_1 = keccak(b'y')

    with pytest.raises(ValueError):
        compute_merkle_tree([hash_0, hash_0])

    with pytest.raises(ValueError):
        compute_merkle_tree([hash_0, hash_1, hash_0])


def test_compute_merkle_tree_no_entry():
    merkle_tree = compute_merkle_tree([])

    assert is_empty_merkle_root(merkle_tree.layers[-1][0])
    assert is_empty_merkle_root(get_merkle_root(merkle_tree))


def test_compute_merkle_tree_single_entry():
    hash_0 = keccak(b'x')
    merkle_tree = compute_merkle_tree([hash_0])

    assert merkle_tree.layers[-1][0] == hash_0
    assert get_merkle_root(merkle_tree) == hash_0


def test_get_merkle_root_one():
    hash_0 = b'a' * 32

    leaves = [hash_0]
    merkle_tree = compute_merkle_tree(leaves)
    root = get_merkle_root(merkle_tree)

    assert root == hash_0

    proof = compute_merkle_proof(merkle_tree, hash_0)

    assert proof == []
    assert root == hash_0
    assert validate_merkle_proof(proof, root, hash_0) is True


def test_get_merkle_root_two():
    hash_0 = b'a' * 32
    hash_1 = b'b' * 32

    leaves = [hash_0, hash_1]
    merkle_tree = compute_merkle_tree(leaves)
    root = get_merkle_root(merkle_tree)

    assert root == keccak(hash_0 + hash_1)

    proof0 = compute_merkle_proof(merkle_tree, hash_0)
    proof1 = compute_merkle_proof(merkle_tree, hash_1)

    assert proof0 == [hash_1]
    assert root == keccak(hash_0 + hash_1)
    assert validate_merkle_proof(proof0, root, hash_0)

    assert proof1 == [hash_0]
    assert root == keccak(hash_0 + hash_1)
    assert validate_merkle_proof(proof1, root, hash_1)


def test_get_merkle_root_three():
    hash_0 = b'a' * 32
    hash_1 = b'b' * 32
    hash_2 = b'c' * 32

    leaves = [hash_0, hash_1, hash_2]
    merkle_tree = compute_merkle_tree(leaves)
    root = get_merkle_root(merkle_tree)

    hash_01 = (
        b'me\xef\x9c\xa9=5\x16\xa4\xd3\x8a\xb7\xd9\x89\xc2\xb5\x00'
        b'\xe2\xfc\x89\xcc\xdc\xf8x\xf9\xc4m\xaa\xf6\xad\r['
    )
    assert keccak(hash_0 + hash_1) == hash_01
    calculated_root = keccak(hash_2 + hash_01)

    assert root == calculated_root

    proof0 = compute_merkle_proof(merkle_tree, hash_0)
    proof1 = compute_merkle_proof(merkle_tree, hash_1)
    proof2 = compute_merkle_proof(merkle_tree, hash_2)

    assert proof0 == [hash_1, hash_2]
    assert root == calculated_root
    assert validate_merkle_proof(proof0, root, hash_0)

    assert proof1 == [hash_0, hash_2]
    assert root == calculated_root
    assert validate_merkle_proof(proof1, root, hash_1)

    # with an odd number of values, the last value wont appear by itself in the
    # proof since it isn't hashed with another value
    assert proof2 == [keccak(hash_0 + hash_1)]
    assert root == calculated_root
    assert validate_merkle_proof(proof2, root, hash_2)


def test_get_merkle_root_many(tree_up_to=20):
    for number_of_leaves in range(1, tree_up_to):  # skipping the empty tree

        leaves = [
            keccak(str(value).encode())
            for value in range(number_of_leaves)
        ]

        merkle_tree = compute_merkle_tree(leaves)
        root = get_merkle_root(merkle_tree)

        for value in leaves:
            proof = compute_merkle_proof(merkle_tree, value)
            assert validate_merkle_proof(proof, root, value)

        reversed_tree = compute_merkle_tree(reversed(leaves))
        assert root == get_merkle_root(reversed_tree)
