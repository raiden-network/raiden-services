class TransactionTooEarlyException(Exception):
    """
    Raised when a transaction is submitted too early.
    Generally caused by the difference in clock between the node and the blockchain.
    """
