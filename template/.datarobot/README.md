### **DataRobot Internal Resources**

#### 📌 **Overview**
This directory (`.datarobot/`) contains DataRobot internal resources that should not be copied
to the repos inside the `datarobot-community` GitHub organization during the release process.

#### 🔒 **Resources**
Below is a list of the resources included in this repository:

| Resource                      | Purpose                                                                                    |
|-------------------------------|--------------------------------------------------------------------------------------------|
| `.datarobot/sync-exclude.yml` | Configuration for the Harness release pipeline.                                            |
| `.datarobot/base-answers.yml` | Will be used to load the last user's answers to the questions made in the copier.yml file. |
| `.datarobot/.harness/`        | Harness CI/CD configurations and related tooling.                                          |

---

See [copier](https://copier.readthedocs.io/en/stable/) documentation to find out more about the templating system.
