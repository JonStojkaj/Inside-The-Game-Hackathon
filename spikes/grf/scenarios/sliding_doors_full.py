# 11 vs 11 like GRF's 11_vs_11_stochastic, but with configurable length and balance.
# Mounted into gfootball/scenarios/ by the recorder (see record_match.py).
#   GRF_DURATION          steps (0.1 s each); 54000 = a real 90 minutes, GRF default is 3000
#   GRF_LEFT_DIFFICULTY   built-in AI strength of the left team ("home"), 0..1
#   GRF_RIGHT_DIFFICULTY  same for the right team ("away"); GRF's default 0.6 makes home win most games

#   GRF_VARIANT           in deterministic mode GRF ignores the seed; a non-zero variant nudges the
#                         kick-off positions (reproducibly) so each variant is a different deterministic match

import os
import random

from . import *

_rng = random.Random(int(os.environ.get('GRF_VARIANT', '0')))
_jitter = 0.015 if os.environ.get('GRF_VARIANT', '0') != '0' else 0.0


def _add(builder, x, y, role):
  if role != e_PlayerRole_GK:
    x += _rng.uniform(-_jitter, _jitter)
    y += _rng.uniform(-_jitter, _jitter)
  builder.AddPlayer(x, y, role)


def build_scenario(builder):
  global _rng
  _rng = random.Random(int(os.environ.get('GRF_VARIANT', '0')))  # fresh per build: warm-up envs must not shift it
  builder.config().game_duration = int(os.environ.get('GRF_DURATION', '54000'))
  builder.config().left_team_difficulty = float(os.environ.get('GRF_LEFT_DIFFICULTY', '0.9'))
  builder.config().right_team_difficulty = float(os.environ.get('GRF_RIGHT_DIFFICULTY', '0.9'))
  # deterministic=1 makes headless and rendered runs of the same seed identical (pick a match fast, render it later)
  builder.config().deterministic = os.environ.get('GRF_DETERMINISTIC', '0') == '1'
  builder.SetTeam(Team.e_Left)
  _add(builder, -1.000000, 0.000000, e_PlayerRole_GK)
  _add(builder, 0.000000,  0.020000, e_PlayerRole_RM)
  _add(builder, 0.000000, -0.020000, e_PlayerRole_CF)
  _add(builder, -0.422000, -0.19576, e_PlayerRole_LB)
  _add(builder, -0.500000, -0.06356, e_PlayerRole_CB)
  _add(builder, -0.500000, 0.063559, e_PlayerRole_CB)
  _add(builder, -0.422000, 0.195760, e_PlayerRole_RB)
  _add(builder, -0.184212, -0.10568, e_PlayerRole_CM)
  _add(builder, -0.267574, 0.000000, e_PlayerRole_CM)
  _add(builder, -0.184212, 0.105680, e_PlayerRole_CM)
  _add(builder, -0.010000, -0.21610, e_PlayerRole_LM)
  builder.SetTeam(Team.e_Right)
  _add(builder, -1.000000, 0.000000, e_PlayerRole_GK)
  _add(builder, -0.050000, 0.000000, e_PlayerRole_RM)
  _add(builder, -0.010000, 0.216102, e_PlayerRole_CF)
  _add(builder, -0.422000, -0.19576, e_PlayerRole_LB)
  _add(builder, -0.500000, -0.06356, e_PlayerRole_CB)
  _add(builder, -0.500000, 0.063559, e_PlayerRole_CB)
  _add(builder, -0.422000, 0.195760, e_PlayerRole_RB)
  _add(builder, -0.184212, -0.10568, e_PlayerRole_CM)
  _add(builder, -0.267574, 0.000000, e_PlayerRole_CM)
  _add(builder, -0.184212, 0.105680, e_PlayerRole_CM)
  _add(builder, -0.010000, -0.21610, e_PlayerRole_LM)
