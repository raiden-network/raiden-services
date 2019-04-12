CREATE TABLE blockchain (
    chain_id                        INTEGER,
    receiver                        CHAR(42),
    token_network_registry_address  CHAR(42),
    latest_known_block              INT,
    user_deposit_contract_address   CHAR(42)
);

CREATE TABLE token_network (
    address                 CHAR(42) PRIMARY KEY
);

INSERT INTO blockchain DEFAULT VALUES;
CREATE TABLE iou (
    sender TEXT NOT NULL,
    amount HEX_INT NOT NULL,
    expiration_block HEX_INT NOT NULL,
    signature TEXT NOT NULL,
    claimed BOOL NOT NULL,
    PRIMARY KEY (sender, expiration_block)
);
CREATE UNIQUE INDEX one_active_session_per_sender
    ON iou(sender) WHERE NOT claimed;
