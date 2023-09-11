import os.path
from argparse import ArgumentParser
from awscrt import io
from awsiot.greengrass_discovery import DiscoveryClient

parser = ArgumentParser("Discover core device credentials")
parser.add_argument(
    "--broker_thing_name", required=True, help="The IoT thing name of the broker device"
)
parser.add_argument(
    "--client_thing_name", required=True, help="The IoT thing name of the client device"
)
parser.add_argument(
    "--thing_cert_path",
    required=True,
    help="The path to the X.509 cert of the client device",
)
parser.add_argument(
    "--thing_key_path",
    required=True,
    help="The path to the X.509 cert's key for the client device",
)
parser.add_argument(
    "--region", required=True, help="The AWS region of the broker device"
)
parser.add_argument("--ca_path", help="The path to the root CA file")
parser.add_argument(
    "--output_cert_path", required=True, help="The path to write the broker's CA to"
)
parser.add_argument(
    "--output_ip_path", required=True, help="The path to write the broker's IP to"
)
parser.add_argument(
    "--output_port_path", required=True, help="The path to write the broker's port to"
)
parser.add_argument(
    "--force_rediscovery",
    type=bool,
    required=True,
    help="Whether discovery should happen if the files already exist",
)
args = parser.parse_args()

target_thing = args.broker_thing_name
thing_name = args.client_thing_name
cert = args.thing_cert_path
key = args.thing_key_path
region = args.region
ca = args.ca_path
output_cert_path = args.output_cert_path
output_ip_path = args.output_ip_path
output_port_path = args.output_port_path
force_rediscovery = args.force_rediscovery


if not force_rediscovery:
    if (
        os.path.isfile(output_cert_path)
        and os.path.isfile(output_ip_path)
        and os.path.isfile(output_port_path)
    ):
        print("found existing connectivity information, exiting.")
        exit(0)


tls_options = io.TlsContextOptions.create_client_with_mtls_from_path(cert, key)
if ca is not None:
    tls_options.override_default_trust_store_from_path(None, ca)
tls_context = io.ClientTlsContext(tls_options)
socket_options = io.SocketOptions()
discovery_client = DiscoveryClient(
    io.ClientBootstrap.get_or_create_static_default(),
    socket_options,
    tls_context,
    region,
)

discover_response = discovery_client.discover(thing_name).result()

ip = None
port = None
ca = None
for gg_group in discover_response.gg_groups:
    if gg_group.gg_group_id.endswith(target_thing):
        c = gg_group.cores[0].connectivity[0]
        ip = c.host_address
        port = c.port
        ca = gg_group.certificate_authorities[0]
        break

if ip is None or port is None or ca is None:
    raise SystemExit(
        f"error: could not retrieve connectivity info: {discover_response}"
    )
else:
    with open(output_cert_path, "w") as f:
        f.write(ca)
    with open(output_ip_path, "w") as f:
        f.write(ip)
    with open(output_port_path, "w") as f:
        f.write(str(port))

    print(
        f"wrote connectivity information to {output_cert_path}, {output_ip_path}, {output_port_path}"
    )
