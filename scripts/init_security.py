"""Create local TLS CA/server certificate and identity-service secrets; never overwrite."""
import argparse
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='deploy/secrets')
    args = parser.parse_args()
    root = Path(args.output)
    tls = root / 'tls'
    tls.mkdir(parents=True, exist_ok=True)
    for name in ('keycloak-db-password', 'keycloak-admin-password', 'grafana-password'):
        if not (root / name).exists():
            with (root / name).open('x') as output:
                output.write(secrets.token_urlsafe(32))
    if any(tls.iterdir()):
        raise FileExistsError('TLS directory is not empty; refusing implicit certificate rotation')
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'IoT local development CA')])
    ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
          .not_valid_after(now + timedelta(days=365)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
          .sign(key, hashes.SHA256()))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    names = [x509.DNSName(name + '.localhost') for name in ('auth', 'registry', 'ingest', 'data', 'portal')]
    names += [x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]
    server = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'IoT local')]))
              .issuer_name(subject).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=90))
              .add_extension(x509.SubjectAlternativeName(names), False)
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), True).sign(key, hashes.SHA256()))
    for name, cert in [('ca.crt', ca), ('server.crt', server)]:
        (tls / name).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    for name, private in [('ca.key', key), ('server.key', server_key)]:
        (tls / name).write_bytes(private.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    print('Local TLS material created. Trust ca.crt explicitly in development; use a public CA for deployment.')


if __name__ == '__main__':
    main()
