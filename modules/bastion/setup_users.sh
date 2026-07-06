#!/bin/bash

# Create SSH directory for ec2-user
mkdir -p /home/ec2-user/.ssh
chmod 700 /home/ec2-user/.ssh
touch /home/ec2-user/.ssh/authorized_keys

# Inject all keys passed by Terraform
cat << 'EOF' > /home/ec2-user/.ssh/authorized_keys
%{ for key in keys ~}
${key}
%{ endfor ~}
EOF

chmod 600 /home/ec2-user/.ssh/authorized_keys
chown ec2-user:ec2-user /home/ec2-user/.ssh -R

echo "✔ SSH keys deployed with cloud-init"