#!/bin/bash
# -*- coding: utf-8-unix; mode: Text -*-

module load gcc/11.2.0
module load python/3.8/3.8.13
module load cuda/11.0/11.0.3
module load cudnn/8.0/8.0.5
source ~/tfenv/bin/activate
python mnist_convnet.py $1 128 15
deactivate
