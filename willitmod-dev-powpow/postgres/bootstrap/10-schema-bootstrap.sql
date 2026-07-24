CREATE TABLE IF NOT EXISTS shares
(
	poolid TEXT NOT NULL,
	blockheight BIGINT NOT NULL,
	difficulty DOUBLE PRECISION NOT NULL,
	actualdifficulty DOUBLE PRECISION NOT NULL DEFAULT 0,
	networkdifficulty DOUBLE PRECISION NOT NULL,
	miner TEXT NOT NULL,
	worker TEXT NULL,
	useragent TEXT NULL,
	ipaddress TEXT NOT NULL,
	source TEXT NULL,
	created TIMESTAMPTZ NOT NULL
);

ALTER TABLE shares ADD COLUMN IF NOT EXISTS actualdifficulty DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE shares ADD COLUMN IF NOT EXISTS source TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_shares_pool_miner ON shares(poolid, miner);
CREATE INDEX IF NOT EXISTS idx_shares_pool_created ON shares(poolid, created);
CREATE INDEX IF NOT EXISTS idx_shares_pool_miner_difficulty ON shares(poolid, miner, difficulty);

CREATE TABLE IF NOT EXISTS blocks
(
	id BIGSERIAL PRIMARY KEY,
	poolid TEXT NOT NULL,
	type TEXT NULL,
	chain TEXT NOT NULL,
	blockheight BIGINT NOT NULL,
	networkdifficulty DOUBLE PRECISION NOT NULL,
	status TEXT NOT NULL,
	confirmationprogress FLOAT NOT NULL DEFAULT 0,
	effort FLOAT NULL,
	transactionconfirmationdata TEXT NOT NULL,
	miner TEXT NULL,
	reward DECIMAL(28,8) NULL,
	source TEXT NULL,
	hash TEXT NULL,
	created TIMESTAMPTZ NOT NULL
);

DO $$
BEGIN
	IF NOT EXISTS (
		SELECT 1
		FROM pg_constraint
		WHERE conname = 'blocks_pool_height'
	) THEN
		ALTER TABLE blocks
			ADD CONSTRAINT blocks_pool_height UNIQUE (poolid, chain, blockheight) DEFERRABLE INITIALLY DEFERRED;
	END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_blocks_pool_block_status ON blocks(poolid, chain, blockheight, status);

CREATE TABLE IF NOT EXISTS balances
(
	poolid TEXT NOT NULL,
	chain TEXT NOT NULL,
	address TEXT NOT NULL,
	amount DECIMAL(28,8) NOT NULL DEFAULT 0,
	created TIMESTAMPTZ NOT NULL,
	updated TIMESTAMPTZ NOT NULL,
	PRIMARY KEY (poolid, chain, address)
);

CREATE TABLE IF NOT EXISTS balance_changes
(
	id BIGSERIAL PRIMARY KEY,
	poolid TEXT NOT NULL,
	chain TEXT NOT NULL,
	address TEXT NOT NULL,
	amount DECIMAL(28,8) NOT NULL DEFAULT 0,
	usage TEXT NULL,
	tags TEXT[] NULL,
	created TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_balance_changes_pool_address_created ON balance_changes(poolid, chain, address, created DESC);
CREATE INDEX IF NOT EXISTS idx_balance_changes_pool_tags ON balance_changes USING gin (tags);

CREATE TABLE IF NOT EXISTS miner_settings
(
	poolid TEXT NOT NULL,
	address TEXT NOT NULL,
	paymentthreshold DECIMAL(28,8) NOT NULL,
	created TIMESTAMPTZ NOT NULL,
	updated TIMESTAMPTZ NOT NULL,
	PRIMARY KEY (poolid, address)
);

CREATE TABLE IF NOT EXISTS payments
(
	id BIGSERIAL PRIMARY KEY,
	poolid TEXT NOT NULL,
	chain TEXT NOT NULL,
	address TEXT NOT NULL,
	amount DECIMAL(28,8) NOT NULL,
	transactionconfirmationdata TEXT NOT NULL,
	created TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payments_pool_coin_wallet ON payments(poolid, chain, address);

CREATE TABLE IF NOT EXISTS poolstats
(
	id BIGSERIAL PRIMARY KEY,
	poolid TEXT NOT NULL,
	connectedminers INT NOT NULL DEFAULT 0,
	connectedworkers INT NOT NULL DEFAULT 0,
	poolhashrate DOUBLE PRECISION NOT NULL DEFAULT 0,
	sharespersecond DOUBLE PRECISION NOT NULL DEFAULT 0,
	networkhashrate DOUBLE PRECISION NOT NULL DEFAULT 0,
	networkdifficulty DOUBLE PRECISION NOT NULL DEFAULT 0,
	lastnetworkblocktime TIMESTAMPTZ NULL,
	blockheight BIGINT NOT NULL DEFAULT 0,
	connectedpeers INT NOT NULL DEFAULT 0,
	created TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_poolstats_pool_created ON poolstats(poolid, created);

CREATE TABLE IF NOT EXISTS minerstats
(
	id BIGSERIAL PRIMARY KEY,
	poolid TEXT NOT NULL,
	miner TEXT NOT NULL,
	worker TEXT NOT NULL,
	hashrate DOUBLE PRECISION NOT NULL DEFAULT 0,
	sharespersecond DOUBLE PRECISION NOT NULL DEFAULT 0,
	created TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_minerstats_pool_created ON minerstats(poolid, created);
CREATE INDEX IF NOT EXISTS idx_minerstats_pool_miner_created ON minerstats(poolid, miner, created);
CREATE INDEX IF NOT EXISTS idx_minerstats_pool_miner_worker_created_hashrate ON minerstats(poolid, miner, worker, created DESC, hashrate);
