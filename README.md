# Cloud IT Final Project__Adele Alsaed

## How to run the Kubernetes Deployment:
1. inject the Azure connection string into the cluster by running this command:
kubectl create secret generic azure-secret --from-literal=azurestorageaccountkey="<ENTER_KEY_HERE>"

2. deploy the backend and frontend:
kubectl apply -f k8s/Backend.yaml
kubectl apply -f k8s/Frontend.yaml

!Note: The Azure Storage Account key has been omitted from this repository to follow security best practices. Please replace <ENTER_KEY_HERE> with the key provided privately in my assignment submission attachment via Moodle!