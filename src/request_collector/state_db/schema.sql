CREATE TABLE metadata (
    chain_id                              INTEGER,
    monitoring_contract_address           CHAR(42),
    receiver                              CHAR(42)
);
INSERT INTO metadata VALUES (
    NULL,
    NULL,
    NULL
);

CREATE TABLE syncstate (
    contract_address        CHAR(42) PRIMARY KEY,
    confirmed_head_number   INTEGER NOT NULL,
    confirmed_head_hash     CHAR(66) NOT NULL,
    unconfirmed_head_number INTEGER NOT NULL,
    unconfirmed_head_hash   CHAR(66) NOT NULL
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

CREATE TABLE monitor_requests (
    channel_identifier HEX_INT     NOT NULL,
    non_closing_signer CHAR(42)    NOT NULL,
    balance_hash       CHAR(34)    NOT NULL,
    nonce              HEX_INT     NOT NULL,
    additional_hash    CHAR(32)    NOT NULL,
    closing_signature  CHAR(34)    NOT NULL,
    non_closing_signature    CHAR(160)   NOT NULL,
    reward_proof_signature   CHAR(42)    NOT NULL,
    reward_amount            HEX_INT     NOT NULL,
    token_network_address    CHAR(42)    NOT NULL,
    PRIMARY KEY (channel_identifier, token_network_address, non_closing_signer)
    FOREIGN KEY (channel_identifier, token_network_address)
        REFERENCES channels(channel_identifier, token_network_address) ON DELETE CASCADE
);
