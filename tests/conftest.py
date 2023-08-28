import os
import shutil
import tempfile
from pathlib import Path
import pytest
from git import Repo


@pytest.fixture(name='git_repo', scope='module')
def fixture_git_repo(request):
    # Create a temporary directory
    repo_dir = tempfile.mkdtemp()

    # Initialize a new Git repository in the temporary directory
    Repo.init(repo_dir)

    # Change the current working directory to the temporary directory
    prev_cwd = os.getcwd()
    os.chdir(repo_dir)

    # Add a cleanup function to remove the temporary directory after the test
    def cleanup():
        os.chdir(prev_cwd)
        shutil.rmtree(repo_dir)

    request.addfinalizer(cleanup)
    return repo_dir


@pytest.fixture
def mock_home_dir(tmp_path):
    home_dir = Path(tmp_path / 'home')
    home_dir.mkdir()

    original_home = os.environ.get('HOME')
    os.environ['HOME'] = str(home_dir)

    yield home_dir

    if original_home is not None:
        os.environ['HOME'] = original_home
    else:
        del os.environ['HOME']
