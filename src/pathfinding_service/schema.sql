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
