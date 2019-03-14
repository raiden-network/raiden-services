CREATE TABLE iou (
    sender TEXT NOT NULL,
    amount HEXINT NOT NULL,
    expiration_block HEXINT NOT NULL,
    signature TEXT NOT NULL,
    PRIMARY KEY (sender, expiration_block)
);
