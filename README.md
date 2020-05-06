# aether-stream-consumer
Aether Consumer that performs operations based on streaming input.

At a high level the purpose of this consumer is to subscribe to input from a system (currently either Apache Kafka or Zeebe) perform some actions based on the input, possibly transforming it, and then return a signal to the original system. This can be arranged in semi-arbitrary ways using a defined `Pipeline`. A pipeline manages a subscription, and orchestrates the movement of data through stages. Each stage has a transformation. This sounds more complicated than it is in practice, and the flexibility allows us to do all sorts of things, combining the power of Kafka, and Zeebe (BPMN) with the ability to perform arbitrary computations.

If you want to get started right away, you can play with this system easily using the build tools in [the Zeebe Tester Repo](https://github.com/eHealthAfrica/zeebe_tester). I highly recommend this as the basic artifacts are already there, and can deploy automatically to the local instance if you modify them. It's by far the best way to get familiar with the system.


### ZeebeInstance `/zeebe`

Zeebe Instance is a basic resource that holds connection information to a Zeebe cluster (or single broker) and allows you to interact with the broker with `Pipelines` to send messages, start workflows, and subscribe to Service Tasks.

You can also communicate directly with the broker through this API to test some functionality.

#### test

`zeebe/test?id={resource-id}` : GET

Tests if the broker can be connected to. Returns a boolean

#### send_message
`zeebe/send_message?id={resource-id}` : POST

Send a message to the broker

Options (JSON):
- listener_name         : (required) the intended message listener on the broker
- message_id=None       : optional unique_id for the message (uniqueness enforced if present)
- correlationKey=None   : a key used to deliver this message to a running workflow
- ttl=600_000           : how long the message should be held if it can't be delivered immediately
- variables = {}        : any data that you want to include with the message

#### start_workflow
`zeebe/start_workflow?id={resource-id}`: POST

Start a workflow on the broker

Options (JSON):
 - process_id           : the ID of the process you want to start
 - variables = {}       : and date you want to include in the workflow context
 - version = 1          : the deployed version of the process to target


## Transformation

The most basic in this application is the `Transformation`. There are a few types. Some are only useful in conjunction with Zeebe, but others are general purpose. They're all basically small functional units that take input and provide an output. Unlike other Aether Consumers, these resource don't require a lot of definition up front. Except for JSCall, you likely only need one of each with a definition of:

```
{
    "id": "default",
    "name": "The default implementation"
}
```
But you know that since you already checked out [the Zeebe Tester Repo](https://github.com/eHealthAfrica/zeebe_tester)


![Diagram](/doc/Selection_009.jpg)

Currently we have the following types of Transformations (XFs). Scroll down to see the section on testing XFs directly.

#### Rest Call `/restcall`

Make a http request based on the input parameters. This XF is based on the python requests library. It can take any of the following arguments:
```
method,
url,
headers=None,
token=None,
basic_auth=None,
query_params=None,
json_body=None,
form_body=None,
allow_redirects=False,

```
On success, RestCall returns:
```
encoding
headers
status_code
text
json  (if applicable)
request_failed = False
```
On failure, RestCall returns:
```
encoding
reason
status_code
request_failed = True
```

Please note that all url must be resolved by the Google DNS service. This attempts to disallow access to network internals via this transform.


#### JavaScript Call `/jscall`

JS Call is powered by a sandboxed javascript environment based on `quickjs`. This is the only Transform that requires a specific definition. You define include an arbitrary piece of javascript which is executed at runtime on the input you define. *quickjs does not have networking* and some other higher level functions enabled, so you are limited to calculations you can perform in context, which is quite a lot. You can also require libraries which can be used by your function. You must define your own JSCalls before they can be run. There are a few in `/app/fixtures/examples.py`. Just remember if it needs to communicate (send an email, write to S3, etc), you _can't_ do it with JSCall.

Here is a definition for a JSCall that turns a piece of JSON into a CSV. Do note that the value of the `script` field _must_ be a valid JSON string. That is to say, it should be minified, then escaped. The following is presented expanded to illustrate and is not valid as it has line breaks.

```
{
    "id": "parser",
    "name": "CSV Parser",
    "entrypoint": "f",
    "script": "
    function f(myData) {
        const Parser = json2csv.Parser;
        const fields = [/"a/", /"b/"];
        const opts = { fields };
        try {
          const parser = new Parser(opts);
          return parser.parse(myData);
        } catch (err) {
          console.error(err);
        }
    }
    ",
    "arguments": ["jsonBody"],
    "libraries": ["https://cdn.jsdelivr.net/npm/json2csv@4.2.1/dist/json2csv.umd.js"]
}
```
This function would require the argument `jsonBody` and then return the stringified CSV as `"value": {the csv}`.

You can also type you arguments like:
```
"arguments": {"arg_a": "str", "arg_b": "int"}
```


#### ZeebeMessage `/zeebemessage`

This transform will broadcast a message to Zeebe. You cannot test this transform directly, as it requires a Zeebe Broker be in context. You can send adhoc messages to a Zeebe broker by posting to `/zeebe/send_message?id=broker-id`

```
listener_name   # the message listener on the broker you're targeting
message_id      # (optional, ids must be unique at any given time)
variables       # (optional) an object with any data you want to pass
correlationKey  # (optional) the Zeebe correlation key
```


#### ZeebeSpawn `/zeebespawn`

This transform will attempt to kick off a new workflow instance in Zeebe with data your provide. You cannot test this transform directly, as it requires a Zeebe Broker be in context. You can adhoc spawn workflows on a Zeebe broker by posting to `/zeebe/start_workflow?id=broker-id`

```
process_id     # the ID of the Zeebe Process
variables      # (optional) an object with any data you want to pass
version        # (optional) the workflow version you're trying to start
```

#### ZeebeComplete `/zeebecomplete`

This is the most specific transform, and will complete an in process ZeebeJob. This only works in a pipeline context that subscribed to a ZeebeJob. It takes a look at the passed in data, and based on a jsonpath evaluation either tells the broker that the job was successful or failed.




#### Testing Transforms

Each type of transform can be accessed, created and tested individually through the API.

If you had created the above jscall, you would test is by posting a JSON payload to:

`{consumer_url}/jscall/test?id=parser`

In this case, it would fail if you don't have "jsonBody" as one of the keys in your JSON payload.

If you post a properly formatted payload (for the instance) like:
```
{
  "jsonBody": {
    "a": 1, "b": 2
  }
}
```
You the the correct result, a CSV (as an escaped string):
```
{
  "result": "\"a\",\"b\"\n1,2"
}
```
## Stage

One level up from a transform, we have a `Stage`. A stage describes the input and output from a `Transformation`, and optionally provides validation criteria to be evaluated against an output. 

![Diagram](/doc/Selection_010.jpg)

Stages are not themselves resources, as they operate on context specific data. I.E. the proper input map of a stage will be dependent on the outputs of previous stages, or the expected input from a subscription. Stages are combined in the next level of the hierarchy, `Pipeline`, but since they are highly configurable, they get their own section here. They include the following:
 - name         : name of the stage, used as the key for it's output
 - type         : type of the Transformation to be used
 - id           : instance of the Transform to be used
 - transition   : the transition definition (input / output map && validation) 

Here is an example of a single stage:
```
{
    'name': 'one',
    'type': 'jscall',
    'id': 'strictadder',
    'transition': {
        'input_map': {
            'a': '$.source.value',
            'b': '$.const.one'
        },
        'output_map': {
            'result': '$.result'
        },
        'fail_condition': '$.result.`match(0, null)`'

    }
}
```

The input map and output map are both expressed as a set of JSONPath expressions, which can incorporate extensions as described [at the eHA JSONPath Extensions page](https://github.com/eHealthAfrica/jsonpath-extensions/).

The input map describes the parameters to be passed to a `Transformation`. 

Take the referenced JSCall Transformation for example:
```
{
    'id': 'strictadder',
    'name': 'Adder with Type Checking',
    'entrypoint': 'f',
    'script': '''
        function adder(a, b) {
        return a + b;
    }
    function f(a, b) {
        return adder(a, b);
    }

    ''',
    'arguments': {'a': 'int', 'b': 'int'}
}
```
It expects integer arguments named `a` and `b`, so those must be included in out input map from some source. A reasonable input map then might be:
```
{
    "a": "$.some.path.to.an.integer",
    "b": "$.a.path.to.another.integer"
}
```
Additionally you can add validation to the transition. This is expressed as a JSONPath expression that should evaluate to a boolean.
```
'fail_condition': '$.result.`match(0, null)`'
```
This isn't a very useful condition, but we've indicated here that we should fail if the result of `strictadder` is `0`. This is more useful for status_codes from the RESTCall transform, etc.


## Pipeline

A `Pipeline` is where concepts come together into an actionable set of behaviors. 

![Diagram](/doc/Selection_011.jpg)

It consists of two primary things.
 - A `subscription`. A data source that which at the moment can either be a set of Kafka Topics or a cursor to incoming instances of a Zeebe Service Task of a particular type.
 - An ordered set of `stages` which transform the input.

 As a pipeline runs, it carries a `context`, which allows each state to reference the source message from the subscription, a set of user defined constants, and the output of each previous stage. The constants for the pipeline are set when the resource is defined.

Here is a very simple and pretty dumb pipeline, which uses the `strictadder` JSCall Transformation we used in the stages example.

```
{
    'id': 'adder_example',
    'zeebe_instance': 'default',
    'zeebe_subscription': 'adder-worker',
    'const': {
        'one': 1,
    },
    'stages': [
        {
            'name': 'one',
            'type': 'jscall',
            'id': 'strictadder',
            'transition': {
                'input_map': {
                    'a': '$.source.value',
                    'b': '$.const.one'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        },
        {
            'name': 'two',
            'type': 'jscall',
            'id': 'strictadder',
            'transition': {
                'input_map': {
                    'a': '$.one.result',
                    'b': '$.const.one'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        },
        {
            'name': 'three',
            'type': 'jscall',
            'id': 'strictadder',
            'transition': {
                'input_map': {
                    'a': '$.two.result',
                    'b': '$.const.one'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        },
        {
            'name': 'four',
            'type': 'zeebecomplete',
            'id': 'default',
            'transition': {
                'input_map': {
                    'added_value': '$.three.result'
                }
            }
        }
    ]
}
```
You can see that the source of data here is a Zeebe ServiceTask of type `adder-worker` from which we expect an integer as input (`$.source.value`). From there, we have three identical stages that each add 1 to the value of the previous stage. At stage 4, we return the value from stage three via a `zeebecomplete` Transformation.

Most pipelines should be quite simple, since you want to perform all logic in Zeebe when possible. Pipelines should source, transmit, transform or validate data, not sort it or perform a lot of logic.

### Testing Pipelines

Just like individual Transformations, once you have a Pipeline Resource registered, you can test it directly without side effect by posting a message to the test endpoint at `{consumer_url}/pipeline/test?id={pipeline-id}`. This is highly recommended to test for behavior and edge cases before adding it to a job where it runs automatically.

In the case that a Zeebe operation is set to occur as part of the pipeline you're testing, that step will be skipped without Zeebe interaction. Zeebe interactions can be tested directly against a running broker.

To test, POST your test payload to `{consumer_url}/pipeline/test?id={pipeline-id}`.
If successful, the result will be the completed Pipeline Context. Otherwise, errors will help you to debug your Pipeline. For example, this 400 error that arose from an RESTCall Transform not receiving a url.
```
On Stage "one": TransformationError: Expected required fields, missing ['url']
```





![Diagram](/doc/Selection_012.jpg)

![Diagram](/doc/Selection_013.jpg)

![Diagram](/doc/Selection_014.jpg)

![Diagram](/doc/Selection_015.jpg)
