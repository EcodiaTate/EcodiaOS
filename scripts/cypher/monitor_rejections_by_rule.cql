MATCH (:PolicyArm {id:'noop_arm'})-[:HAS_CONSTRAINT]->(r:Rule)
WITH r.rejection_reason AS reason
MATCH (:PolicyArm)-[:HAS_CONSTRAINT]->(rr:Rule {rejection_reason: reason})
OPTIONAL MATCH (a:PolicyArm {id: rr.arm_id}) // tolerate if not present
RETURN reason, count(rr) AS rules_defined
ORDER BY rules_defined DESC;
