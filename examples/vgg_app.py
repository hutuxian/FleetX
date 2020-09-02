# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import fleetx as X
import paddle
import paddle.distributed.fleet as fleet
# FleetX help users to focus more on learning to train a large scale model
# if you want to learn how to write a model, FleetX is not for you
# focus more on engineering staff in fleet-x

configs = X.parse_train_configs()

model = X.applications.VGG16()
imagenet_downloader = X.utils.ImageNetDownloader()
local_path = imagenet_downloader.download_from_bos(local_path='./data')
loader = model.load_imagenet_from_file(
    "{}/train.txt".format(local_path), data_layout='NCHW')

fleet.init(is_collective=True)
dist_strategy = fleet.DistributedStrategy()
dist_strategy.amp = True

optimizer = paddle.optimizer.Momentum(
    learning_rate=configs.lr,
    momentum=configs.momentum,
    weight_decay=paddle.fluid.regularizer.L2Decay(0.0001))
optimizer = fleet.distributed_optimizer(optimizer, strategy=dist_strategy)
optimizer.minimize(model.loss)

trainer = X.MultiGPUTrainer()
trainer.fit(model, loader, epoch=10)
