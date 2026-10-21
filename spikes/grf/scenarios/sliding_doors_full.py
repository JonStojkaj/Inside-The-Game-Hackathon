# 11 vs 11 like GRF's 11_vs_11_stochastic, but with configurable length and balance.
# Mounted into gfootball/scenarios/ by the recorder (see record_match.py).
#   GRF_DURATION          steps (0.1 s each); 54000 = a real 90 minutes, GRF default is 3000
#   GRF_LEFT_DIFFICULTY   built-in AI strength of the left team ("home"), 0..1
#   GRF_RIGHT_DIFFICULTY  same for the right team ("away"); GRF's default 0.6 makes home win most games

import os

from . import *


def build_scenario(builder):
  builder.config().game_duration = int(os.environ.get('GRF_DURATION', '54000'))
  builder.config().left_team_difficulty = float(os.environ.get('GRF_LEFT_DIFFICULTY', '0.9'))
  builder.config().right_team_difficulty = float(os.environ.get('GRF_RIGHT_DIFFICULTY', '0.9'))
  builder.config().deterministic = False
  builder.SetTeam(Team.e_Left)
  builder.AddPlayer(-1.000000, 0.000000, e_PlayerRole_GK)
  builder.AddPlayer(0.000000,  0.020000, e_PlayerRole_RM)
  builder.AddPlayer(0.000000, -0.020000, e_PlayerRole_CF)
  builder.AddPlayer(-0.422000, -0.19576, e_PlayerRole_LB)
  builder.AddPlayer(-0.500000, -0.06356, e_PlayerRole_CB)
  builder.AddPlayer(-0.500000, 0.063559, e_PlayerRole_CB)
  builder.AddPlayer(-0.422000, 0.195760, e_PlayerRole_RB)
  builder.AddPlayer(-0.184212, -0.10568, e_PlayerRole_CM)
  builder.AddPlayer(-0.267574, 0.000000, e_PlayerRole_CM)
  builder.AddPlayer(-0.184212, 0.105680, e_PlayerRole_CM)
  builder.AddPlayer(-0.010000, -0.21610, e_PlayerRole_LM)
  builder.SetTeam(Team.e_Right)
  builder.AddPlayer(-1.000000, 0.000000, e_PlayerRole_GK)
  builder.AddPlayer(-0.050000, 0.000000, e_PlayerRole_RM)
  builder.AddPlayer(-0.010000, 0.216102, e_PlayerRole_CF)
  builder.AddPlayer(-0.422000, -0.19576, e_PlayerRole_LB)
  builder.AddPlayer(-0.500000, -0.06356, e_PlayerRole_CB)
  builder.AddPlayer(-0.500000, 0.063559, e_PlayerRole_CB)
  builder.AddPlayer(-0.422000, 0.195760, e_PlayerRole_RB)
  builder.AddPlayer(-0.184212, -0.10568, e_PlayerRole_CM)
  builder.AddPlayer(-0.267574, 0.000000, e_PlayerRole_CM)
  builder.AddPlayer(-0.184212, 0.105680, e_PlayerRole_CM)
  builder.AddPlayer(-0.010000, -0.21610, e_PlayerRole_LM)
