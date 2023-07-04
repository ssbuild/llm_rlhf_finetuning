# -*- coding: utf-8 -*-
# @Time    : 2023/5/17 14:26
import json
import os
import numpy as np
import torch
from deep_training.data_helper import ModelArguments, DataArguments
from tqdm import tqdm
from transformers import HfArgumentParser,AutoConfig,PreTrainedTokenizer
from data_utils import train_info_args, NN_DataHelper
from aigc_zoo.model_zoo.llm.rrhf_model import MyRRHFTransformer
from aigc_zoo.model_zoo.llm.reward_model import MyRewardTransformer
from stage3_rrhf.data_processer import tokenizer_one

if __name__ == '__main__':
    train_info_args['seed'] = None
    parser = HfArgumentParser((ModelArguments, DataArguments))
    model_args, data_args = parser.parse_dict(train_info_args,allow_extra_keys=True)

    tokenizer : PreTrainedTokenizer
    dataHelper = NN_DataHelper(model_args, None, data_args)
    tokenizer, _, _, _ = dataHelper.load_tokenizer_and_config()

    ckpt_dir = './stage2_reward/best_ckpt'
    config = AutoConfig.from_pretrained(ckpt_dir)

    pl_model = MyRewardTransformer(config=config, model_args=model_args)
    # 加载权重
    pl_model.load_sft_weight(ckpt_dir)

    pl_model.eval().half().cuda()
    pl_model.requires_grad_(False)


    def predict_data(filename):
        with open(filename, mode='r', encoding='utf-8') as f:
            lines = f.readlines()
        D = []
        for line in tqdm(lines, total=len(lines)):
            jd = json.loads(line)
            if not jd:
                continue
            input_list = [
                tokenizer_one(tokenizer, jd['prompt'], jd['chosen'], max_length=512),
                tokenizer_one(tokenizer, jd['prompt'], jd['rejected'], max_length=512)
            ]
            tokend = tokenizer(input_list, padding=True, truncation=True)
            input_ids = torch.tensor(tokend["input_ids"], dtype=torch.int32).to(pl_model.device)
            output = pl_model.backbone.compute_loss(input_ids=input_ids)
            _, scores = output

            D.append({
                "prompt": jd['prompt'],
                "response": [
                    jd['chosen'], jd['rejected'],
                ],
                "score": [
                    scores[0],
                    scores[1]
                ]
            })
        return D


    def dump_to_file(D, file):
        with open(file, mode='w', encoding='utf-8', newline='\n') as f:
            for jd in D:
                f.write(json.dumps(jd, ensure_ascii=True) + '\n')


    dump_to_file(predict_data('./data/train.json'), './data/train_score.json')
    dump_to_file(predict_data('./data/eval.json'), './data/eval_score.json')
