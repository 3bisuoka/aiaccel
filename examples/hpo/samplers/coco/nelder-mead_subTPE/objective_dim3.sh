#!/bin/bash

#$-l rt_C.small=1
#$-cwd
#$ -l h_rt=0:15:00

source /etc/profile.d/modules.sh
module load gcc/13.2.0
module load python/3.10/3.10.14 

python3.10 experiment_for_nm_sampler_subTPE_parallel.py $@
