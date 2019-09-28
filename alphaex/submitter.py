import os
import time
from pathlib import Path


class Submitter(object):
	"""
	Create a job submitter and which will ssh to clusters and submit slurm array jobs.
	
	Args:
		clusters (list): clusters information
		total_num_jobs (int): total number of jobs to run
		duration_between_two_polls (int): duration between two polls in seconds. Default value is 60.
		repo_url (str): experiment code's git repo url. If this is not provide, the user needs to copy experiment code
		to each cluster manually.
	
	The clusters information is stored in a list of dictionaries.
	
	Each dictionary must contain 4 fields:
	
	name (str): the name of your remote cluster, it should be defined in .ssh/config of the server.
	
	capacity (int): maximum number of jobs you want to run in that cluster, usually each cluster provides this information in its user manuel.
	
	project_root_dir (str): the root directory containing the project in the cluster. If repo_url is not None, then submitter
	will clone/pull codebase from github to this directory. Otherwise the user must copy experiment code to this directory manually.
	
	script_path (str): the path of the slurm array job submission script in the remote cluster.
	
	2 Additional fields are optional:
	
	exp_results_from (list): a list of experiment results paths in the cluster
	
	exp_results_to (list): a list of paths where experiment results will be copied to
	
	"""
	def __init__(self, clusters, total_num_jobs, duration_between_two_polls=60, repo_url=None):
		# sanity check
		required_members = ["name", "capacity", "project_root_dir", "script_path"]
		for cluster in clusters:
			for member in required_members:
				if member not in cluster:
					print("%s not defined in clusters" %member)
					exit(1)
			if 'exp_results_from' in cluster and 'exp_results_to' in cluster and cluster['exp_results_from'].__len__() != cluster['exp_results_to'].__len__():
				print("length of list exp_results_from must equal to length of list exp_results_to")
				exit(1)
		
		# code synchronize
		if repo_url is not None:
			for cluster in clusters:
				
				root_path = "/".join(cluster['project_root_dir'].split("/")[:-1])
				project_name = cluster['project_root_dir'].split('/')[-1]
				bash_script = "ssh %s 'if [ -d %s ]; then cd %s; git pull origin master; else cd %s; git clone %s %s; fi'" % (
					cluster['name'], cluster['project_root_dir'], cluster['project_root_dir'], root_path, repo_url, project_name
				)
				print(bash_script)
				myCmd = os.popen(bash_script).read()
				print(myCmd)
				
		# make output_dir
		for cluster in clusters:
			for i in range(len(cluster['exp_results_from'])):
				bash_script = "ssh %s 'mkdir -p %s'" % (cluster['name'], cluster['exp_results_from'][i])
				print(bash_script)
				myCmd = os.popen(bash_script).read()
				print(myCmd)
				
		self.clusters = clusters.copy()
		self.starting_job_num = 0
		self.total_num_jobs = total_num_jobs
		self.duration_between_two_polls = duration_between_two_polls
	
	def submit_jobs(self, num_jobs, cluster_name, project_root_dir, script_path):
		bash_script = "ssh %s 'cd %s; sbatch --array=%d-%d %s'" % (
			cluster_name, project_root_dir, self.starting_job_num, self.starting_job_num + num_jobs - 1, script_path
		)
		print(bash_script)
		myCmd = os.popen(bash_script).read()
		print(myCmd)
		print('submit jobs from %d to %d to %s' % (
			self.starting_job_num, self.starting_job_num + num_jobs - 1, cluster_name
		))
		self.starting_job_num += num_jobs
		if self.starting_job_num >= self.total_num_jobs:
			return True
		return False
	
	def submit(self):
		for cluster in self.clusters:
			bash_script = "ssh %s whoami" % cluster['name']
			print(bash_script)
			myCmd = os.popen(bash_script).read()
			print(myCmd)
			cluster['username'] = myCmd.split('\n')[0]
		
		finish_submitting = False
		temp_clusters = self.clusters.copy()
		while True:
			for cluster in temp_clusters[:]:
				bash_script = "ssh %s squeue -u %s -r" % (cluster['name'], cluster['username'])
				print(bash_script)
				myCmd = os.popen(bash_script).read()
				print(myCmd)
				lines = myCmd.split('\n')
				num_current_jobs = 0
				for line in lines:
					if cluster['script_path'].split('/')[-1] in line:
						num_current_jobs += 1
				print("cluster %s has %d jobs" % (cluster['name'], num_current_jobs))
				
				if finish_submitting:
					if num_current_jobs == 0:
						temp_clusters.remove(cluster)
					if temp_clusters.__len__() == 0:
						print("Finish running all jobs, start copying experiment results back to server")
						for cluster in self.clusters:
							if 'exp_results_from' in cluster and 'exp_results_to' in cluster:
								for i in range(len(cluster['exp_results_from'])):
									Path(cluster['exp_results_to'][i]).mkdir(parents=True, exist_ok=True)
									bash_script = "scp -r %s:%s/* %s/" % (cluster['name'], cluster['exp_results_from'][i], cluster['exp_results_to'][i])
									print(bash_script)
									myCmd = os.popen(bash_script).read()
									print(myCmd)
						print("Finish all experiment results copying.\nDone\n")
						exit(1)
				elif num_current_jobs < cluster['capacity']:
					finish_submitting = self.submit_jobs(
						min(cluster['capacity'] - num_current_jobs, self.total_num_jobs - self.starting_job_num),
						cluster['name'], cluster['project_root_dir'], cluster['script_path']
					)
					if finish_submitting:
						print("Finish submitting all jobs!")
						
			time.sleep(self.duration_between_two_polls)
