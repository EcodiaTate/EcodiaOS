CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT policyarm_id IF NOT EXISTS FOR (p:PolicyArm) REQUIRE p.id IS UNIQUE;
CREATE INDEX episode_mode_created IF NOT EXISTS FOR (e:Episode) ON (e.mode, e.created_at);
CREATE INDEX policyarm_mode IF NOT EXISTS FOR (p:PolicyArm) ON (p.mode);
