# aether-stream-consumer
Aether Consumer that performs operations based on streaming input.

At a high level the purpose of this consumer is to subscribe to input from a system (currently either Apache Kafka or Zeebe) perform some actions based on the input, possibly transforming it, and then return a signal to the original system. This can be arranged in semi-arbitrary ways using a defined `Pipeline`. A pipeline manages a subscription, and orchestrates the movement of data through stages. Each stage has a transformation. This sounds more complicated than it is in practice, and the flexibility allows us to do all sorts of things, combining the power of Kafka, and Zeebe (BPMN) with the ability to perform arbitrary computations.

If you want to get started right away, you can play with this system easily using the build tools in [the Zeebe Tester Repo](https://github.com/eHealthAfrica/zeebe_tester). I highly recommend this as the basic artifacts are already there, and can deploy automatically to the local instance if you modify them. It's by far the best way to get familiar with the system.


##Transformation

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

JS Call is powered by a sandboxed javascript environment based on `quickjs`. This is the only Transform that requires a specific definition. You define include an arbitrary piece of javascript which is executed at runtime on the input you define. quickjs does not have networking and some other higher level functions enabled, so you are limited to calculations you can perform in context, which is quite a lot. You can also require libraries which can be used by your function. You must define your own JSCalls before they can be run. There are a few in `/app/fixtures/examples.py`

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




### Testing Transforms

Each type of transform can be accessed, created and tested individually through the API.

If you had created the above jscall, you would test is by posting a JSON payload to:

`{consumer_url}/jscall/test?id=parser`

In this case, it would fail if you don't have "jsonBody" as one of the keys in your JSON payload.

![Diagram](/doc/Selection_010.jpg)

![Diagram](/doc/Selection_011.jpg)

![Diagram](/doc/Selection_012.jpg)

![Diagram](/doc/Selection_013.jpg)

![Diagram](/doc/Selection_014.jpg)

![Diagram](/doc/Selection_015.jpg)
