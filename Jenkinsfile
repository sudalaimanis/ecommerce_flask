pipeline {
    agent any

    environment {
        // Images are named ${DOCKER_REPO}-<service>:<build number>, e.g. sudalaimmanis/flaskapp-web:12
        DOCKER_REPO      = 'sudalaimmanis/flaskapp'
        IMAGE_TAG        = "${BUILD_NUMBER}"
        // Directory names under services/ -> image suffix (order_processing -> order-processing)
        SERVICES         = 'web user customer product pricing inventory cart order payment order-processing logistics notification'
        // The exact IDs you saved in Jenkins Credentials Manager
        DOCKER_HUB_CREDS = 'docker-hub-credentials'
        GITHUB_CREDS     = 'github-credentials'
        GITHUB_REPO      = 'github.com/sudalaimanis/ecommerce_flask.git'
    }

    stages {
        stage('Clone Repository') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies & Syntax Check') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                    python -m compileall -q services libs
                '''
            }
        }

        stage('Build Docker Images') {
            steps {
                sh '''
                    for svc in $SERVICES; do
                        dir=$(echo $svc | tr '-' '_')
                        echo "Building $DOCKER_REPO-$svc:$IMAGE_TAG"
                        docker build --build-arg SERVICE=$dir -t $DOCKER_REPO-$svc:$IMAGE_TAG .
                    done
                '''
            }
        }

        stage('Trivy Security Scan') {
            steps {
                sh '''
                    for svc in $SERVICES; do
                        trivy image --exit-code 1 --severity HIGH,CRITICAL $DOCKER_REPO-$svc:$IMAGE_TAG
                    done
                '''
            }
        }

        stage('Push to Docker Hub') {
            steps {
                withCredentials([usernamePassword(credentialsId: "${DOCKER_HUB_CREDS}", usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        for svc in $SERVICES; do
                            docker push $DOCKER_REPO-$svc:$IMAGE_TAG
                        done
                    '''
                }
            }
        }

        stage('Update K8s Manifest & Push to GitHub') {
            steps {
                sh '''
                    for svc in $SERVICES; do
                        sed -i "s|image: $DOCKER_REPO-$svc:.*|image: $DOCKER_REPO-$svc:$IMAGE_TAG|g" k8s-files/services.yml
                    done
                '''
                withCredentials([usernamePassword(credentialsId: "${GITHUB_CREDS}", usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
                    sh '''
                        git config user.name "Jenkins CI"
                        git config user.email "jenkins@yourdomain.com"
                        git add k8s-files/services.yml
                        git commit -m "Build #${BUILD_NUMBER}: Update image tags to ${IMAGE_TAG} [skip ci]"
                        git remote set-url origin https://${GH_USER}:${GH_TOKEN}@${GITHUB_REPO}
                        git push origin HEAD:main
                    '''
                }
            }
        }
    }

    post {
        always {
            sh '''
                for svc in $SERVICES; do
                    docker rmi $DOCKER_REPO-$svc:$IMAGE_TAG || true
                done
            '''
            cleanWs()
        }
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed. Check the logs above.'
        }
    }
}
