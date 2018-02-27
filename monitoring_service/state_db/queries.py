DB_CREATION_SQL = """
CREATE TABLE `metadata` (
    `network_id`       INTEGER,
    `contract_address` CHAR(42),
    `receiver`         CHAR(42)
);
CREATE TABLE `syncstate` (
    `confirmed_head_number`   INTEGER,
    `confirmed_head_hash`     CHAR(66),
    `unconfirmed_head_number` INTEGER,
    `unconfirmed_head_hash`   CHAR(66)
);

CREATE TABLE `balance_proofs` (
    `channel_address`   CHAR(42)    NOT NULL,
    `participant1`      CHAR(42)    NOT NULL,
    `participant2`      CHAR(42)    NOT NULL,
    `balance_proof`     CHAR(160)   NOT NULL,
    `timestamp`         INT         NOT NULL
);
INSERT INTO `metadata` VALUES (
    NULL,
    NULL,
    NULL
);
INSERT INTO `syncstate` VALUES (
    NULL,
    NULL,
    NULL,
    NULL
);
"""


ADD_BALANCE_PROOF_SQL = """
INSERT OR REPLACE INTO `balance_proofs` VALUES (
    ?, ?, ?, ?, ?
);"""

UPDATE_METADATA_SQL = """
UPDATE `metadata` SET
    `network_id` = ?,
    `contract_address` = ?,
    `receiver` = ?;
"""
