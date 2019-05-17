CREATE TABLE blockchain (
    chain_id                        INTEGER,
    receiver                        CHAR(42),
    token_network_registry_address  CHAR(42),
    monitor_contract_address        CHAR(42),
    latest_known_block              INT
);
INSERT INTO blockchain DEFAULT VALUES;


CREATE TABLE token_network (
    address                 CHAR(42) PRIMARY KEY
);


CREATE TABLE channel (
    token_network_address   CHAR(42) NOT NULL,
    identifier              HEX_INT  NOT NULL,
    participant1            CHAR(42) NOT NULL,
    participant2            CHAR(42) NOT NULL,
    settle_timeout          HEX_INT  NOT NULL,
    -- see raiden_contracts.constants.ChannelState for value meaning
    state                   INT NOT NULL CHECK (state >= 0 AND state <= 4),
    closing_block           HEX_INT,
    closing_participant     CHAR(42),
    closing_tx_hash         CHAR(66),
    claim_tx_hash           CHAR(66),
    update_status_sender    CHAR(42),
    update_status_nonce     HEX_INT,
    PRIMARY KEY (identifier, token_network_address),
    FOREIGN KEY (token_network_address)
        REFERENCES token_network(address),
    -- make sure that all update_status fields are NULL at the same time
    CHECK ((update_status_sender IS NULL) = (update_status_nonce IS NULL))
);

CREATE TABLE monitor_request (
    channel_identifier      HEX_INT     NOT NULL,
    token_network_address   CHAR(42)    NOT NULL,

    balance_hash            CHAR(66)    NOT NULL,
    nonce                   HEX_INT     NOT NULL,
    additional_hash         CHAR(66)    NOT NULL,
    closing_signature       CHAR(132)   NOT NULL,

    non_closing_signature   CHAR(132)   NOT NULL,
    reward_amount           HEX_INT     NOT NULL,
    reward_proof_signature  CHAR(132)   NOT NULL,

    non_closing_signer      CHAR(42)    NOT NULL,
    PRIMARY KEY (channel_identifier, token_network_address, non_closing_signer)
    --FOREIGN KEY (channel_identifier, token_network_address)
    --    REFERENCES channels(channel_identifier, token_network_address) ON DELETE CASCADE
);

CREATE TABLE waiting_transactions (
    transaction_hash        CHAR(66)    NOT NULL
);

CREATE TABLE scheduled_events (
    trigger_block_number    HEX_INT     NOT NULL,
    event_type              INT NOT NULL CHECK (event_type >= 0 AND event_type <=1),

    token_network_address   CHAR(42)    NOT NULL,
    channel_identifier      HEX_INT     NOT NULL,
    non_closing_participant CHAR(42)    NOT NULL,

    PRIMARY KEY (trigger_block_number, event_type, token_network_address, channel_identifier, non_closing_participant),
    FOREIGN KEY (token_network_address)
        REFERENCES token_network(address)
);
