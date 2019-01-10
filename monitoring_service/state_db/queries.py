DB_CREATION_SQL = """

CREATE TABLE `metadata` (
    `chain_id`                              INTEGER,
    `monitoring_contract_address`           CHAR(42),
    `receiver`                              CHAR(42)
);
INSERT INTO `metadata` VALUES (
    NULL,
    NULL,
    NULL
);

CREATE TABLE `syncstate` (
    `confirmed_head_number`   INTEGER,
    `confirmed_head_hash`     CHAR(66),
    `unconfirmed_head_number` INTEGER,
    `unconfirmed_head_hash`   CHAR(66)
);
INSERT INTO `syncstate` VALUES (
    NULL,
    NULL,
    NULL,
    NULL
);

CREATE TABLE channels (
    channel_identifier      HEX_INT  NOT NULL,
    token_network_address   CHAR(42) NOT NULL,
    participant1            CHAR(42) NOT NULL,
    participant2            CHAR(42) NOT NULL,
    -- see raiden_contracts.constants.ChannelState for value meaning
    state         INT NOT NULL CHECK (state >= 0 AND state <= 4),
    PRIMARY KEY (channel_identifier, token_network_address)
);

-- transferred_amount is uint256
-- reward_amount is uint192
-- nonce is uint64
CREATE TABLE `monitor_requests` (
    `channel_identifier` HEX_INT     NOT NULL,
    `non_closing_signer` CHAR(42)    NOT NULL,
    `balance_hash`       CHAR(34)    NOT NULL,
    `nonce`              HEX_INT     NOT NULL,
    `additional_hash`    CHAR(32)    NOT NULL,
    `closing_signature`  CHAR(34)    NOT NULL,
    `non_closing_signature`    CHAR(160)   NOT NULL,
    `reward_proof_signature`   CHAR(42)    NOT NULL,
    `reward_amount`            HEX_INT     NOT NULL,
    `token_network_address`    CHAR(42)    NOT NULL,
    PRIMARY KEY (channel_identifier, token_network_address, non_closing_signer)
    FOREIGN KEY (channel_identifier, token_network_address)
        REFERENCES channels(channel_identifier, token_network_address) ON DELETE CASCADE
);
"""


ADD_MONITOR_REQUEST_SQL = """
INSERT OR REPLACE INTO `monitor_requests` VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
);"""

UPDATE_METADATA_SQL = """
UPDATE `metadata` SET
    `chain_id` = ?,
    `monitoring_contract_address` = ?,
    `receiver` = ?;
"""
