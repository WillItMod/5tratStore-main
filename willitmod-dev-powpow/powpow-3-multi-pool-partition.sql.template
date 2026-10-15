SET ROLE mergedmining;

/* WARNING - this will drop all your shares */
DROP TABLE shares;

CREATE TABLE shares
(
	poolid TEXT NOT NULL,
	blockheight BIGINT NOT NULL,
	difficulty DOUBLE PRECISION NOT NULL,
	networkdifficulty DOUBLE PRECISION NOT NULL,
	miner TEXT NOT NULL,
	worker TEXT NULL,
	useragent TEXT NULL,
	ipaddress TEXT NOT NULL,
    source TEXT NULL,
	created TIMESTAMP WITH TIME ZONE NOT NULL
) PARTITION BY LIST (poolid);

CREATE INDEX IDX_SHARES_CREATED ON SHARES(created);
CREATE INDEX IDX_SHARES_MINER_DIFFICULTY on SHARES(miner, difficulty);

/* Repeat for every pool */
/* CREATE TABLE shares_<poolname> PARTITION OF shares FOR VALUES IN ('<poolname>');*/
CREATE TABLE shares_testing PARTITION OF shares FOR VALUES IN ('testing');