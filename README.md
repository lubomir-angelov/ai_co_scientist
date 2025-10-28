# ai_co_scientist
An agentic framework for an ai co-scientist. 

Based on the Octotols framework: https://github.com/octotools/octotools

The agent focuses on three main capabilities: 
  1. Deep technical reasoning + math skill
  2. Long context window (to ingest papers, specs, layouts)
  3. Ability to generate and critique code / architectures.
  
An additional feature is the ability to run consumer-grade hardware.

# Setup
The repo was cloned from the octotools and was moved to a new repo keeping the original history up to this point.

## Pre-requisites:
1. A clean new repo in your own github
2. A classic token (or new one) with Repo level permissions (or All repos)
3. Environment vars with your github credentials.

```bash
export GITHUB_USER_NAME=#your-user-name#
export GITHUB_PAT=#your-personal-access-token-noquotes#
export GITHUB_PERSONAL_REPO_NAME=#your-personal-repo-name#
```

## 1. Get the source + history
```bash
git clone https://${GITHUB_PAT}@github.com/octotools/octotools.git ${GITHUB_PERSONAL_REPO_NAME}
cd ai_co_scientist
```

## 2. Detach from the original GitHub origin
```bash
git remote remove origin
```

## 3. Add your own new (empty) repo as origin
```bash
git remote add origin "https://${GITUB_USER_NAME}$:${GITHUB_PAT}@github.com/lubomir-angelov/${GITHUB_PERSONAL_REPO_NAME}.git"
```

## 4. Push all branches and tags (optional but usually good)
git push -u origin --all
git push origin --tags

## (optional) 5. Keep a reference to original for updates
git remote add upstream https://github.com/original-user/octotools.git
git fetch upstream



# Citation

@article{lu2025octotools,
    title={OctoTools: An Agentic Framework with Extensible Tools for Complex Reasoning},
    author={Lu, Pan and Chen, Bowen and Liu, Sheng and Thapa, Rahul and Boen, Joseph and Zou, James},
    journal = {arXiv preprint arXiv:2502.11271},
    year={2025}
}
