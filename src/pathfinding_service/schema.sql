CREATE TABLE iou (
    sender TEXT NOT NULL,
    amount HEXINT NOT NULL,
    expiration_block HEXINT NOT NULL,
    signature TEXT NOT NULL,
    claimed BOOL NOT NULL,
    PRIMARY KEY (sender, expiration_block)
);
CREATE UNIQUE INDEX one_active_session_per_sender
    ON iou(sender) WHERE NOT claimed;
