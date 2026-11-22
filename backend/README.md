Stage 1 (Global): 
- Implement a cost-weighted A* or Dijkstra pathfinder on a 2D Florida grid using static forecast weather + battery burn costs. Output a clean list of waypoints.

Stage 2 (Local RL): 
- Train a PPO agent in Gymnasium whose only job is to fly from point A to point B while dodging moving storm blobs and staying close to the straight line connecting A and B.

Stage 3 (HITL Wrapper): 
- Connect them so Stage 1 feeds sequential waypoints to Stage 2, and add a simple UI or threshold check that flags the human whenever cross-track deviation or battery drop exceeds limits.