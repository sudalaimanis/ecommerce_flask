pipeline {
    agent any

    environment {
        DOCKER_REPO      = 'sudalaimmanis/flaskapp'
        IMAGE_TAG        = "${BUILD_NUMBER}"
        // The exact IDs you saved in Jenkins Credentials Manager
        DOCKER_HUB_CREDS = 'docker-hub-credentials' 
        GITHUB_CREDS     = 'github-credentials'
    }

    stages {
        stage('Clone Repository') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies & Lint') {
            steps {
                echo 'Setting up environment and testing dependencies...'
                sh '''
                    python3 -m venv .venv
                    source .venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                echo "Building Docker image: ${DOCKER_REPO}:${IMAGE_TAG}"
                sh "docker build -t ${DOCKER_REPO}:${IMAGE_TAG} ."
            }
        }

        stage('Trivy Security Scan') {
            steps {
                echo "Scanning image ${DOCKER_REPO}:${IMAGE_TAG} for vulnerabilities..."
                sh "trivy image --exit-code 1 --severity HIGH,CRITICAL ${DOCKER_REPO}:${IMAGE_TAG}"
            }
        }

        stage('Push to Docker Hub') {
            steps {
                echo 'Logging into Docker Hub and pushing image...'
                // Securely binds Docker credentials to temporary environment variables
                withCredentials([usernamePassword(credentialsId: "${DOCKER_HUB_CREDS}", usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                    sh "echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin"
                    sh "docker push ${DOCKER_REPO}:${IMAGE_TAG}"
                }
            }
        }

        stage('Update K8s Manifest & Push to GitHub') {
            steps {
                echo 'Updating image tag in deployment.yaml...'
                sh """
                    sed -i 's|image: ${DOCKER_REPO}:.*|image: ${DOCKER_REPO}:${IMAGE_TAG}|g' k8s-files/deployment.yml
                """
                
                echo 'Committing and pushing updated manifest back to GitHub...'
                // Securely binds GitHub credentials to push the manifest change
                withCredentials([usernamePassword(credentialsId: "${GITHUB_CREDS}", usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
                    sh '''
                        git config user.name "Jenkins CI"
                        git config user.email "jenkins@yourdomain.com"
                        git add k8s-files/deployment.yaml
                        git commit -m "Build #${BUILD_NUMBER}: Update image tag to ${IMAGE_TAG} [skip ci]"
                        
                        # Overrides the origin URL to authenticate via the GitHub Personal Access Token
                        git remote set-url origin https://${GH_USER}:${GH_TOKEN}@://github.com
                        git push origin main
                    '''
                }
            }
        }
    }

    post {
        always {
            echo 'Cleaning up workspace...'
            cleanWs()
            sh "docker rmi ${DOCKER_REPO}:${IMAGE_TAG} || true"
        }
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed. Check the logs above.'
        }
    }
}
