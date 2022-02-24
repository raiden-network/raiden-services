CREATE TABLE blockchain (
    chain_id                        INTEGER,
    receiver                        CHAR(42),
    token_network_registry_address  CHAR(42),
    latest_committed_block          INT,
    user_deposit_contract_address   CHAR(42)
);
INSERT INTO blockchain DEFAULT VALUES;

CREATE TABLE token_network (
    address                 CHAR(42) PRIMARY KEY,
    settle_timeout          HEX_INT
);

CREATE TABLE channel (
    token_network_address   CHAR(42) NOT NULL,
    channel_id      HEX_INT NOT NULL,
    participant1    CHAR(42) NOT NULL,
    participant2    CHAR(42) NOT NULL,

    -- From PFSCapacityUpdate
    capacity1       HEX_INT NOT NULL,
    reveal_timeout1 HEX_INT NOT NULL,
    update_nonce1   HEX_INT,
    capacity2       HEX_INT NOT NULL,
    reveal_timeout2 HEX_INT NOT NULL,
    update_nonce2   HEX_INT,

    -- From PFSFeeUpdate
    fee_schedule1   JSON,
    fee_schedule2   JSON,

    PRIMARY KEY (token_network_address, channel_id),
    -- Lexicographical sorting is the same as sorting by value once we remove
    -- the EIP-55 checksumming
    CHECK (lower(participant1) < lower(participant2)),
    UNIQUE (token_network_address, participant1, participant2),
    FOREIGN KEY (token_network_address)
        REFERENCES token_network(address)
);

CREATE TABLE iou (
    sender CHAR(42) NOT NULL,
    amount HEX_INT NOT NULL,
    claimable_until HEX_INT NOT NULL,
    signature CHAR(132) NOT NULL,
    claimed BOOL NOT NULL,
    one_to_n_address CHAR(42) NOT NULL,
    PRIMARY KEY (sender, claimable_until)
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
    source_address CHAR(42) NOT NULL,
    target_address CHAR(42) NOT NULL,
    route TEXT NOT NULL,
    estimated_fee HEX_INT NOT NULL,
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
