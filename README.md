# MICC - Market Intelligence Command Center

## Layout

  D:\MICC\                    <- Intelligence layer
  D:\MICC\data_pipeline\     <- Data extraction pipeline
  D:\marketDB\                <- 53GB database (not moved)

## Daily Commands

  # Update data (after 3:30 PM IST)
  cd D:\MICC\data_pipeline
  py run_pipeline.py

  # Run engine
  cd D:\MICC
  py micc_engine.py 7 --send

  # Dashboard
  cd D:\MICC\micc-dashboard
  npm run dev

  # Health check
  cd D:\MICC\data_pipeline
  py run_pipeline.py --check