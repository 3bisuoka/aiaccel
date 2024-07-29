#!/bin/bash

#$-l rt_C.small=1
#$-cwd
#$ -l h_rt=1:20:00

source /etc/profile.d/modules.sh
module load gcc/13.2.0
module load python/3.10/3.10.14 

python3.10 experiment_for_TPE_sampler_parallel.py $@
