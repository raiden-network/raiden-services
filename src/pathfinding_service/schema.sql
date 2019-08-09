CREATE TABLE blockchain (
    chain_id                        INTEGER,
    receiver                        CHAR(42),
    token_network_registry_address  CHAR(42),
    latest_commited_block           INT,
    user_deposit_contract_address   CHAR(42)
);
INSERT INTO blockchain DEFAULT VALUES;

CREATE TABLE token_network (
    address                 CHAR(42) PRIMARY KEY
);

CREATE TABLE channel_view (
    token_network_address   CHAR(42) NOT NULL,
    channel_id      HEX_INT NOT NULL,
    participant1    CHAR(42) NOT NULL,
    participant2    CHAR(42) NOT NULL,
    settle_timeout  HEX_INT NOT NULL,
    capacity        HEX_INT NOT NULL,
    reveal_timeout  HEX_INT NOT NULL,
    update_nonce    HEX_INT,
    fee_schedule_sender    JSON,
    fee_schedule_receiver  JSON,
    PRIMARY KEY (token_network_address, channel_id, participant1),
    FOREIGN KEY (token_network_address)
        REFERENCES token_network(address)
);

CREATE TABLE iou (
    sender CHAR(42) NOT NULL,
    amount HEX_INT NOT NULL,
    expiration_block HEX_INT NOT NULL,
    signature CHAR(132) NOT NULL,
    claimed BOOL NOT NULL,
    one_to_n_address CHAR(42) NOT NULL,
    PRIMARY KEY (sender, expiration_block)
);

CREATE UNIQUE INDEX one_active_session_per_sender
    ON iou(sender) WHERE NOT claimed;

CREATE TABLE capacity_update (
    updating_participant CHAR(42) NOT NULL,
    token_network_address CHAR(42) NOT NULL,
    channel_id HEX_INT NOT NULL,
    updating_capacity HEX_INT NOT NULL,
    other_capacity HEX_INT NOT NULL,
    PRIMARY KEY (updating_participant, token_network_address, channel_id)
);

CREATE TABLE feedback (
    token_id CHAR(32) NOT NULL,
    creation_time TIMESTAMP NOT NULL,
    token_network_address CHAR(42) NOT NULL,
    route TEXT NOT NULL,
    successful BOOLEAN CHECK (successful IN (0,1)),
    feedback_time TIMESTAMP,
    PRIMARY KEY (token_id, token_network_address, route)
);

CREATE INDEX feedback_successful
    ON feedback(successful);

-- Messages which can't be processed yet because the ChannelOpened event has
-- not been confirmed at the time of receiving will be stored here. The
-- messages are processed when the corresponding ChannelOpened is confirmed.
CREATE TABLE waiting_message (
    token_network_address   CHAR(42) NOT NULL,
    channel_id              HEX_INT NOT NULL,
    message                 JSON NOT NULL,
    added_at                TIMESTAMP DEFAULT current_timestamp,
    FOREIGN KEY (token_network_address)
        REFERENCES token_network(address)
)
