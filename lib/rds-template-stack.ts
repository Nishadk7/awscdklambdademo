import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';

export class RdsTemplateStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ✅ VPC (public only for simplicity)
    const vpc = new ec2.Vpc(this, 'MyVPC', {
      maxAzs: 2,
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
      ],
    });

    // ✅ Security Group (allow MySQL access)
    const sg = new ec2.SecurityGroup(this, 'RDSSG', {
      vpc,
      allowAllOutbound: true,
      description: 'Allow MySQL access',
    });

    sg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(3306),
      'Allow MySQL access from anywhere'
    );

    // ✅ RDS Instance
    const db = new rds.DatabaseInstance(this, 'MyRDS', {
      engine: rds.DatabaseInstanceEngine.mysql({
        version: rds.MysqlEngineVersion.VER_8_0_40,
      }),

      vpc,

      // 🔥 IMPORTANT FIX (public subnet)
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },

      securityGroups: [sg],

      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO
      ),

      allocatedStorage: 20,
      credentials: rds.Credentials.fromGeneratedSecret('admin'),
      databaseName: 'testdb',

      publiclyAccessible: true,

      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ✅ RDS Outputs
    new cdk.CfnOutput(this, 'DBEndpoint', {
      value: db.dbInstanceEndpointAddress,
    });

    new cdk.CfnOutput(this, 'DBPort', {
      value: db.dbInstanceEndpointPort,
    });

    // ✅ DynamoDB Table
    const table = new dynamodb.Table(this, 'MyDynamoTable', {
      tableName: 'UsersTable',

      partitionKey: {
        name: 'userId',
        type: dynamodb.AttributeType.STRING,
      },

      sortKey: {
        name: 'createdAt',
        type: dynamodb.AttributeType.STRING,
      },

      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,

      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ✅ DynamoDB Output
    new cdk.CfnOutput(this, 'DynamoTableName', {
      value: table.tableName,
    });
  }
}