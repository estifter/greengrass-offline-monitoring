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


if not args.force_rediscovery:
    if (
        os.path.isfile(args.output_cert_path)
        and os.path.isfile(args.output_ip_path)
        and os.path.isfile(args.output_port_path)
    ):
        print("found existing connectivity information, exiting.")
        exit(0)


tls_options = io.TlsContextOptions.create_client_with_mtls_from_path(
    args.thing_cert_path, args.thing_key_path
)
if args.ca_path is not None:
    tls_options.override_default_trust_store_from_path(None, args.ca_path)
tls_context = io.ClientTlsContext(tls_options)
socket_options = io.SocketOptions()
discovery_client = DiscoveryClient(
    io.ClientBootstrap.get_or_create_static_default(),
    socket_options,
    tls_context,
    args.region,
)

discover_response = discovery_client.discover(args.client_thing_name).result()

ip = None
port = None
ca = None
for gg_group in discover_response.gg_groups:
    if gg_group.gg_group_id.endswith(args.broker_thing_name):
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
    with open(args.output_cert_path, "w") as f:
        f.write(ca)
    with open(args.output_ip_path, "w") as f:
        f.write(ip)
    with open(args.output_port_path, "w") as f:
        f.write(str(port))

    print(
        f"wrote connectivity information to {args.output_cert_path}, {args.output_ip_path}, {args.output_port_path}"
    )
