# aether-stream-consumer
Aether Consumer that performs operations based on streaming input.

At a high level the purpose of this consumer is to subscribe to input from a system (currently either Apache Kafka or Zeebe) perform some actions based on the input, possibly transforming it, and then return a signal to the original system. This can be arranged in semi-arbitrary ways using a defined `Pipeline`. A pipeline manages a subscription, and orchestrates the movement of data through stages. Each stage has a transformation. This sounds more complicated than it is in practice, and the flexibility allows us to do all sorts of things, combining the power of Kafka, and Zeebe (BPMN) with the ability to perform arbitrary computations.

If you want to get started right away, you can play with this system easily using the build tools in [the Zeebe Tester Repo](https://github.com/eHealthAfrica/zeebe_tester).


The most basic Unit 

![Diagram](/doc/Selection_009.jpg)

![Diagram](/doc/Selection_010.jpg)

![Diagram](/doc/Selection_011.jpg)

![Diagram](/doc/Selection_012.jpg)

![Diagram](/doc/Selection_013.jpg)

![Diagram](/doc/Selection_014.jpg)

![Diagram](/doc/Selection_015.jpg)
