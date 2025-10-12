# systems/synapse/training/hall_of_fame_promoter.py
# NEW FILE

from __future__ import annotations

import asyncio
import logging

from core.utils.neo.cypher_query import cypher_query

logger = logging.getLogger(__name__)

# --- Promotion Criteria ---
# An arm must have at least this many trials to be considered for promotion.
MIN_TRIALS_FOR_PROMOTION = 100
# An arm's average reward must be in this top percentile of all arms in its mode.
PROMOTION_PERCENTILE_THRESHOLD = 95.0


class HallOfFamePromoter:
    """
    Analyzes historical performance of all PolicyArms and promotes the elite
    performers to the "Hall of Fame" to ensure long-term knowledge retention.
    """

    async def run_promotion_cycle(self):
        """
        Executes a full cycle of analysis and promotion.
        """
        logger.info("[HallOfFame] Starting promotion cycle...")

        # 1. Fetch performance statistics for all arms with sufficient trial data.
        # This query aggregates the reward and counts trials for every arm.
        query_stats = """
        MATCH (e:Episode)
        WHERE e.chosen_arm_id IS NOT NULL AND e.reward IS NOT NULL
        WITH e.chosen_arm_id AS arm_id, count(e) AS trials, avg(e.reward) AS avg_reward
        WHERE trials >= $min_trials
        MATCH (p:PolicyArm {id: arm_id})
        RETURN
            p.id AS arm_id,
            p.mode AS mode,
            trials,
            avg_reward
        """
        try:
            arm_stats = (
                await cypher_query(query_stats, {"min_trials": MIN_TRIALS_FOR_PROMOTION}) or []
            )
        except Exception as e:
            logger.error(f"[HallOfFame] Failed to query arm performance statistics: {e}")
            return

        if not arm_stats:
            logger.info(
                "[HallOfFame] No arms meet the minimum trial count for promotion analysis. Ending cycle."
            )
            return

        # 2. Group stats by mode to find the promotion threshold for each cognitive style.
        stats_by_mode = {}
        for stat in arm_stats:
            mode = stat.get("mode")
            if mode:
                stats_by_mode.setdefault(mode, []).append(stat)

        # 3. Identify the arms that qualify for promotion.
        promotable_arms = []
        for mode, stats in stats_by_mode.items():
            if not stats:
                continue

            # Find the reward threshold for this mode (e.g., the 95th percentile reward).
            rewards = [s["avg_reward"] for s in stats]
            # Using a simple percentile calculation. A more robust implementation might use numpy.
            rewards.sort()
            percentile_index = int(len(rewards) * (PROMOTION_PERCENTILE_THRESHOLD / 100.0))
            reward_threshold = (
                rewards[percentile_index] if percentile_index < len(rewards) else rewards[-1]
            )

            logger.info(
                f"[HallOfFame] Mode '{mode}' has a promotion reward threshold of {reward_threshold:.4f}."
            )

            # Find all arms in this mode that exceed the threshold.
            for arm_stat in stats:
                if arm_stat["avg_reward"] >= reward_threshold:
                    promotable_arms.append(arm_stat)

        if not promotable_arms:
            logger.info("[HallOfFame] No arms met the promotion criteria in this cycle.")
            return

        # 4. Persist the promotions in Neo4j.
        # This query marks an arm as a Hall of Fame member and stores its stats.
        query_promote = """
        UNWIND $arms AS arm_data
        MATCH (p:PolicyArm {id: arm_data.arm_id})
        MERGE (hof:HallOfFameArm {id: arm_data.arm_id})
        SET hof.promoted_at = datetime(),
            hof.mode = arm_data.mode,
            hof.avg_reward_at_promotion = arm_data.avg_reward,
            hof.trials_at_promotion = arm_data.trials
        MERGE (p)-[:IN_HALL_OF_FAME]->(hof)
        """
        try:
            await cypher_query(query_promote, {"arms": promotable_arms})
            promoted_ids = [arm["arm_id"] for arm in promotable_arms]
            logger.info(
                f"[HallOfFame] Successfully promoted {len(promotable_arms)} arms: {promoted_ids}"
            )
        except Exception as e:
            logger.error(f"[HallOfFame] Failed to persist promotions to the graph: {e}")


# Singleton instance for the daemon to call
hall_of_fame_promoter = HallOfFamePromoter()
