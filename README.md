# Eikobot AWS module

A module for deploying AWS resources.


## Setup

To use this module, you need to have AWS credentials.
There are currently 2 ways of setting these up:

1) Using the AWS CLI (recommended)
2) Using a set of Access keys

The first method requires [installing and setting up the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).  

The second method requires creating an access key and setting the `AWS_ACCESS_KEY` and `AWS_SECRET_ACCESS_KEY` environment variables.  
If the environment variables are set, this module will always use those instead of the aws cli.  
