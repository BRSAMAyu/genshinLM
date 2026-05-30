import subprocess, sys, os
os.chdir(r"D:\Aurora\vision_agent_kernel_v0_5")
outf = open("_test_output.txt", "w")
r = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=short", "-x"],
    stdout=outf, stderr=subprocess.STDOUT, text=True, cwd=r"D:\Aurora\vision_agent_kernel_v0_5"
)
outf.write(f"\nRETURNCODE: {r.returncode}\n")
outf.close()
