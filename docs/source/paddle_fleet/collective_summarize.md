## 设计综述

### 背景

纵观深度学习的发展史，不难发现，很多奠基性的工作，其实早在上世纪四五十年代就被提出了。但是囿于算力，当时的成果主要集中在理论上。直到最近十年间，随着计算性能的不断提升，我们能够在有限的时间内训练出更大更深的神经网络，才让深度学习得以腾飞。不夸张的说，深度学习如今在各个领域取得的成就，和大规模是分不开的。

不管是学术界还是工业界，都一直致力于更快速的训练更大更深的神经网络。大体来分，我们在深度学习领域主要有两个追求，一是训练性能更快，二是模型规模更大。分布式深度学习领域中的很多概念和技巧，都是为了解决这两个问题产生的。

接下来我们就从性能优化和大模型训练两方面入手，介绍几个常用的方法。

### 性能优化

在通用GPU发布之后，使用显卡训练神经网络的热度开始爆炸性地增长。NVIDIA的CUDA编程语言可以让用户以一种像C一样的语言实现任意代码。那么如何在通用GPU上设计出高效的代码，对性能提升就变得至关重要。本小节大部分的内容，正是关注于此。值得一提的是，除了GPU，市场上还涌现了很多其他硬件厂商开发的AI专用芯片，例如百度的昆仑、华为的昇腾910等。当然，在这些不同芯片上的优化思路都是比较类似的。

在分布式机器学习中，最常用的并行模式是数据并行，即每个工作节点拥有全部模型参数，并训练全量数据的一部分，之后对参数（或者其梯度）进行通信（通常为all-reduce操作）以实现全局信息共享。在数据并行模式下，最简单的做法是每个参数的梯度计算出来之后，进行一次通信。可以看出，计算和通信是分布式深度学习任务中最主要的两部分。所以常用的性能优化策略也正是从这两部分入手进行的。

#### 计算OP融合

在深度学习框架中，最基本的计算单元是算子（Operator）。例如常见的矩阵乘法操作，就是以MatMul算子的形式存在。一个完整的计算网络，通常就是由多个算子组合起来的。这样的设计十分灵活，用户可以通过组合不同的算子来验证不同的想法。

但是，鱼和熊掌不可兼得。拥有巨大灵活性所要付出的代价就是性能。举例来讲，假设我们要计算三个输入a、b、c相加的结果，调用过程可能是`tmp=add(a, b); out=add(tmp, c)`。在这样的网络中，我们会启动两次计算，并开辟了一个中间变量用于存放中间计算结果。在CUDA开发中，这样的一次计算通常是由一个或多个Kernel进行的，而Kernel的启动通常需要一定时间开销。

针对这个操作的一种优化方法是，我们开发一个支持三个输入的OP（假设名为add3）。那么我们只需要启动一次Kernel计算，即`out=add3(a, b, c)`，便可以得到最终的结果。该方法的一个附加好处是还节省了一个临时空间的申请。

这种思路就是所谓的计算OP融合（Fusion)，详细内容请参考[4.1.1小节](https://fleet-x.readthedocs.io/en/latest/paddle_fleet_rst/collective/collective_performance/op_fusion.html#id1)。需要说明的是，OP融合在单卡下就有效果，并不是分布式特有的策略。对分布式训练来讲，如何在计算和通信并重的情况下获得更优秀的性能，是我们关注的重点。

接下来的几个小节会结合一个生动的例子来阐述各种优化策略的思想。我们的主人公是Alice和Bob两位小朋友，他们要在各自的房间里做一沓试卷，每张试卷上有若干题目，覆盖不同的知识点。他们的目标是做完所有的试卷，并学到相应的知识。特别的，他们可以通过交换各自学到的内容来修正或巩固自己的知识。Alice和Bob一开始选定的做法是：每当他们之间有人做完一道题，就拨电话给对方，等对方也做完这道题并接起电话后，同步各自的答案，然后同时开始做下一道题。

#### 通信OP融合
Alice和Bob所在的国家电话号码很长，所以他们发现每做完一道题就互相通话，拨电话号码的耗时有些难以接受。他们想，如果商定好做完多道题目，再通话一次进行交流，能省去很多拨电话号码造成的时间开销。

这就是通信OP融合的思想。我们知道每次触发通信都会有一些额外的操作（如先建立连接等），减少这些额外的操作将对性能有很大帮助[1]。顺着这个思路，如果我们能够将多次通信的内容先拼接成连续的数据，然后在一次通信内全部发送/接收，那么将会更充分的利用硬件资源，获得更大的性能提升。

通信OP融合的使用方法请参考[4.1.2小节](https://fleet-x.readthedocs.io/en/latest/paddle_fleet_rst/collective/collective_performance/op_fusion.html#id2)。


#### 通信重叠
按照之前的约定，做题快的人（比如Alice）拨通电话后，要等待Bob完成对应的题目之后接起电话才能开始这次通信。在等待Bob接听电话的时候，Alice只是闲坐在那里听着听筒里的彩铃音乐。她突然想到，为什么要听这种无聊的声音，而不开始提前做下面的题目呢？

这就是通信和计算重叠的思想。CUDA中有stream[2]的概念，通过令计算和通信操作使用不同的stream，可以做到二者的重叠。详细内容请参考[4.2小节](https://fleet-x.readthedocs.io/en/latest/paddle_fleet_rst/collective/collective_performance/overlap.html)。

#### 通信拓扑优化
现在做题的团队壮大了，除了Alice和Bob，又加入了几位新同学。他们的目标变成要让每个人算出来的答案，都被所有其他人知道。最简单的做法，自然是所有人之间通一次电话。但是这样做时间开销太大了。聪明的他们选择了另一种做法，把所有人分成几组，每个组选出一名组长，组员把答案汇总给组长。组长间先互相交换所有的信息，然后再分发给所有组员。

不同的信息交换策略，对应到分布式训练中，就是不同的通信拓扑。上述采用的通信策略借鉴了分层（hierarchical）通信的思想。在业界，有ring-allreduce[3],Double binary trees[4]等多种拓扑结构。

通信拓扑优化的更多使用方法，请参考[4.3小节](https://fleet-x.readthedocs.io/en/latest/paddle_fleet_rst/collective/collective_performance/communication_topology.html)。

#### 深度梯度压缩
再次回到仅有Alice和Bob两人做题学习的场景来。他们在做题过程中发现，随着学习的进行，对于不同知识点的掌握程度有好有坏。有的知识点已经掌握的很好了，再做题也提供不了太多新的知识。但另外一些，却仍然感到模棱两可。于是两人约定，每做完T张试卷，选出最拿不准的几个知识点来交流答案，而掌握充分的那些知识点，就不在电话中交流了。

上述思路就是深度梯度压缩（Deep Gradient Compression, DGC）的主要思想。DGC通过将梯度稀疏化，在每轮训练时只选择出一部分比较“重要”的梯度进行同步，以达到降低通信量的目的。当然，减少通信量势必会造成精度损失。为了减少损失程度，作者还提出了动量修正(momentum correction)、本地梯度裁剪(local gradient cliping)、动量因子遮蔽(Momentum factor masking) 等几项技巧。详细内容可以参考[4.4.1小节](https://fleet-x.readthedocs.io/en/latest/paddle_fleet_rst/collective/collective_performance/communication_frequency.html#dgc-gpu)。

#### Local SGD
Alice和Bob觉得没必要每道题都打电话交流答案，就算使用了前述通信OP融合的技术，也只是减少了打电话的频率，但还是每一道题都要对答案。

于是两人又想到了一个能够减少打电话次数的主意：他们决定各自先做T张试卷，自行学习梳理各个知识点的知识，然后再通电话交流各个知识点的心得。当按照这个方法执行的时候两人发现，尽管花费在打电话上的时间确实减少了，但副作用是他们各自学到的知识可能不一定准确，交流次数的减少让他们没法及时纠正自己某些错误的理解。随后，他们打算进一步升级沟通的方式：刚开始学习的时候交流频繁一点，当对各个知识点有了大致的了解后，再慢慢降低通话的频率。毕竟具备了基础知识后，只有在题海中遇到新题才能带来新的认识，刷再多重复的题目是没什么意义的。

这个思路，就是Local SGD的主要思想。顾名思义，Local的意思就是各个节点先本地进行若干次SGD更新，然后再同步。通过延长同步间隔来减轻慢节点的影响和减少通信频率，以此提升训练的吞吐。
详细内容可以参考[4.4.2小节](https://fleet-x.readthedocs.io/en/latest/paddle_fleet_rst/collective/collective_performance/communication_frequency.html#local-sgd)。

#### 自动混合精度
Alice和Bob所在国家的人们有一个特殊能力，就是可以只记忆和表述文字一半的内容（类似汉字只记忆偏旁），他们称之为”半字“。不过，尽管”半字“系统博大精深，可以表达大部分的信息，但毕竟容量相比正常文字减小了一半，准确性会稍稍有点偏差。

随着知识点和题目越来越多，Alice和Bob觉得脑子发沉，可能脑容量已经快用完了，而打电话交流的时间也越来越长。于是他们决定用上”半字“系统，这样就释放了大脑中更多的空间，而且打电话交流的内容也随之减半。

在实际应用中，对应”半字“系统的就是半精度（FP16）类型，使用半精度类型进行训练，称之为混合精度训练。混合精度训练有若干好处，例如减小显存使用量，增大通信吞吐等。当然精度的降低会导致数字表示范围的缩小，进而导致比FP32更容易溢出，为了应对这些问题，我们引入了Dynamic loss scaling, op黑白名单等策略来避免。详细内容请参考[4.5小节](https://fleet-x.readthedocs.io/en/latest/paddle_fleet_rst/collective/collective_performance/amp.html)。

### 大模型训练优化

TBA

### 参考资料
[1] [https://developer.nvidia.com/blog/scaling-deep-learning-training-nccl/](https://developer.nvidia.com/blog/scaling-deep-learning-training-nccl/)

[2] [https://developer.nvidia.com/blog/how-overlap-data-transfers-cuda-cc/](https://developer.nvidia.com/blog/how-overlap-data-transfers-cuda-cc/)

[3] [https://github.com/baidu-research/baidu-allreduce](https://github.com/baidu-research/baidu-allreduce)

[4] [https://developer.nvidia.com/blog/massively-scale-deep-learning-training-nccl-2-4](https://developer.nvidia.com/blog/massively-scale-deep-learning-training-nccl-2-4)