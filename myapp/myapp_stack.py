import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_apigateway as apigw
)
from constructs import Construct

class AwsCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # ───────────────────────────────────────────────────────────────
        # 1. Execution Role (matching your real Lambda role)
        # ───────────────────────────────────────────────────────────────
        lambda_role = iam.Role(
            self,
            "KairosAppScriptSidebarFeatureLambdaRole",
            role_name="Kairos-AppScript-Sidebar-Feature-Lambda-Role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Created by Raja Asileti. Used by Backend API team for Create Project feature.",
        )

        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue",
                    "appconfig:GetConfiguration",
                    "lambda:InvokeFunction",
                ],
                resources=["*"],
            )
        )

        # ───────────────────────────────────────────────────────────────
        # 2. Lambda Function Definition
        # ───────────────────────────────────────────────────────────────
        openai_lambda = _lambda.Function(
            self,
            "OpenAIHandler",
            function_name="Kairos-AppScript-Sidebar-Feature-Lambda",
            description="Used by Backend API team for Create Project feature, powering Sidebar to generate student projects.",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="lambda_function.lambda_handler",
            code=_lambda.Code.from_asset("lambda/Kairos-OpenAI-AppScript-SideBar-CreateProject"),
            role=lambda_role,
            memory_size=128,
            ephemeral_storage_size=cdk.Size.gibibytes(0.5),
            timeout=Duration.seconds(220),
            environment={
                "ENVIRONMENT": "staging",
                "APPCONFIG_APP_ID": "p7foawd",
                "APPCONFIG_PROFILE_ID": "o6lur3i",
                "APPCONFIG_ENV_ID_DEV": "tgzwr3f",
                "APPCONFIG_ENV_ID_PROD": "mainryh",
                "OPENAI_SECRET_NAME": "SchoolFuel-OPENAI-API-KEY",
                "APPCONFIG_POLL_INTERVAL_SEC": "60",
            },
        )

        # ───────────────────────────────────────────────────────────────
        # 3. API Gateway (REST API) + /createproject POST route
        # ───────────────────────────────────────────────────────────────
        api = apigw.RestApi(
            self,
            "CreateProjectAPI",
            rest_api_name="Kairos-CreateProject-API",
            description="API for Create Project Lambda (Sidebar OpenAI feature)."
        )

        create_project = api.root.add_resource("createproject")

        create_project.add_method(
            "POST",
            apigw.LambdaIntegration(openai_lambda)
        )
