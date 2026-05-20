@echo off

:: ========================================================================
:: SPDX-FileCopyrightText: 2022-2026 Harald Pretl and Georg Zachl
:: Johannes Kepler University, Department for Integrated Circuits
::.
:: Licensed under the Apache License, Version 2.0 (the "License");
:: you may not use this file except in compliance with the License.
:: You may obtain a copy of the License at
::.
::     http://www.apache.org/licenses/LICENSE-2.0
::.
:: Unless required by applicable law or agreed to in writing, software
:: distributed under the License is distributed on an "AS IS" BASIS,
:: WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
:: See the License for the specific language governing permissions and
:: limitations under the License.
:: SPDX-License-Identifier: Apache-2.0
::
:: This file is based on start_vnc.bat from:
:: https://github.com/iic-jku/IIC-OSIC-TOOLS
::
:: Modifications by Jianxun Zhu:
:: - Changed DEFAULT_DESIGNS from %USERPROFILE%\eda\designs to %CD%\designs
::   to mount the current directory's designs folder instead of user home
:: Modifications by Luighi Viton-Zorrilla:
:: - Added: support for an .env file to load environment variables
:: - Added: support for gLatout installation by GLAYOUT_INSTALL
:: GLAYOUT_REPOSITORY and GLAYOUT_FOLDER env variables
:: ========================================================================

SETLOCAL

SET DEFAULT_DESIGNS=%CD%\designs
set "ENVFILE=.env"

:: Check if the .env file exists
if exist "%ENVFILE%" (
    :: Loop through the file to set variables (simulates 'source')
    for /f "tokens=*" %%i in (%ENVFILE%) do set %%i
)

IF DEFINED DRY_RUN (
	echo This is a dry run, all commands will be printed to the shell ^(Commands printed but not executed are marked with ^$^)!
	SET ECHO_IF_DRY_RUN=ECHO $
)

IF "%DESIGNS%"=="" (
  SET DESIGNS=%DEFAULT_DESIGNS%
)
echo Using/creating designs directory: %DESIGNS%
if not exist "%DESIGNS%" %ECHO_IF_DRY_RUN% mkdir "%DESIGNS%" 

IF "%DOCKER_USER%"=="" SET DOCKER_USER=hpretl
IF "%DOCKER_IMAGE%"=="" SET DOCKER_IMAGE=iic-osic-tools
IF "%DOCKER_TAG%"=="" SET DOCKER_TAG=chipathon26

IF "%CONTAINER_USER%"=="" SET CONTAINER_USER=1000
IF "%CONTAINER_GROUP%"=="" SET CONTAINER_GROUP=1000

IF "%CONTAINER_NAME%"=="" SET CONTAINER_NAME=iic-osic-tools_chipathon_xvnc

IF "%WEBSERVER_PORT%"=="" (
  SET /a WEBSERVER_PORT=80
) ELSE (
  SET /a WEBSERVER_PORT=%WEBSERVER_PORT%
)
echo Webserver port set to %WEBSERVER_PORT%

IF "%VNC_PORT%"=="" (
  SET /a VNC_PORT=5901
) ELSE (
  SET /a VNC_PORT=%VNC_PORT%
)
echo VNC port set to %VNC_PORT%

IF "%JUPYTER_PORT%"=="" SET JUPYTER_PORT=8888

IF %CONTAINER_USER% NEQ 0 if %CONTAINER_USER% LSS 1000 echo WARNING: Selected User ID %CONTAINER_USER% is below 1000. This ID might interfere with User-IDs inside the container and cause undefined behaviour!
IF %CONTAINER_GROUP% NEQ 0 if %CONTAINER_GROUP% LSS 1000 echo WARNING: Selected Group ID %CONTAINER_GROUP% is below 1000. This ID might interfere with Group-IDs inside the container and cause undefined behaviour!

setlocal enabledelayedexpansion

:: Adding support for gLayout installation
if "%GLAYOUT_INSTALL%"=="1" (

    if "!GLAYOUT_REPOSITORY!"=="" (
        set "GLAYOUT_REPOSITORY=git@github.com:ReaLLMASIC/gLayout.git"
    )

    if "!GLAYOUT_FOLDER!"=="" (
        set "GLAYOUT_FOLDER=gLayout"
    )

    if "!GLAYOUT_PATH!"=="" (
        set "GLAYOUT_PATH=libs"
    )

)

IF DEFINED IIC_SERVER_DEPLOYMENT (
  SET PARAMS=""
) ELSE (
  SET PARAMS=--security-opt seccomp=unconfined
)

IF %WEBSERVER_PORT% GTR 0 (
  SET PARAMS=%PARAMS% -p %WEBSERVER_PORT%:80
)

IF %VNC_PORT% GTR 0 (
  SET PARAMS=%PARAMS% -p %VNC_PORT%:5901
)

IF %JUPYTER_PORT% GTR 0 (
  SET PARAMS=%PARAMS% -p %JUPYTER_PORT%:8888
)

IF DEFINED VNC_PW (
  SET PARAMS=%PARAMS% -e VNC_PW=%VNC_PW%
)

if "%GLAYOUT_INSTALL%"=="1" (

    if not "!GLAYOUT_REPOSITORY!"=="" (
        set "DOCKER_EXTRA_PARAMS=!DOCKER_EXTRA_PARAMS! -e GLAYOUT_REPOSITORY=!GLAYOUT_REPOSITORY!"
    )

    if not "!GLAYOUT_FOLDER!"=="" (
        set "DOCKER_EXTRA_PARAMS=!DOCKER_EXTRA_PARAMS! -e GLAYOUT_FOLDER=!GLAYOUT_FOLDER!"
    )

    if not "!GLAYOUT_PATH!"=="" (
        set "DOCKER_EXTRA_PARAMS=!DOCKER_EXTRA_PARAMS! -e GLAYOUT_PATH=!GLAYOUT_PATH!"
    )

)

IF DEFINED DOCKER_EXTRA_PARAMS (
  SET PARAMS=%PARAMS% %DOCKER_EXTRA_PARAMS%
)

docker container inspect %CONTAINER_NAME% 2>&1 | find "Status" | find /i "running"
IF NOT ERRORLEVEL 1 (
    ECHO Container is running! Stop with \"docker stop %CONTAINER_NAME%\" and remove with \"docker rm %CONTAINER_NAME%\" if required.
) ELSE (
    docker container inspect %CONTAINER_NAME% 2>&1 | find "Status" | find /i "exited"
    IF NOT ERRORLEVEL 1 (
        echo Container %CONTAINER_NAME% exists. Restart with \"docker start %CONTAINER_NAME%\" or remove with \"docker rm %CONTAINER_NAME%\" if required.
    ) ELSE (
        echo Container does not exist, creating %CONTAINER_NAME% ...
        %ECHO_IF_DRY_RUN% docker run -d --user %CONTAINER_USER%:%CONTAINER_GROUP% %PARAMS% -v "%DESIGNS%":/foss/designs --name %CONTAINER_NAME% %DOCKER_USER%/%DOCKER_IMAGE%:%DOCKER_TAG%
        IF %WEBSERVER_PORT% GTR 0 (
            IF DEFINED VNC_PW (
                echo [INFO] To access the VNC session, open a browser and navigate to http://localhost:%WEBSERVER_PORT%/?password=%VNC_PW%
            ) ELSE (
                echo [INFO] To access the VNC session, open a browser and navigate to http://localhost:%WEBSERVER_PORT%/?password=abc123
            )
        )
    )
)

:: Check if GLAYOUT_INSTALL is 1
if "%GLAYOUT_INSTALL%"=="1" (

    :: extra steps for gLayout
    :: In Batch, we check if a directory exists by using "if exist folder\"
    if exist "%DESIGNS%\%GLAYOUT_PATH%\%GLAYOUT_FOLDER%\" (
        echo [INFO] gLayout folder exists in repo. Skipping.
    ) else (
        echo [INFO] adding gLayout as submodule
        
        :: Navigate to the target directory
        pushd "%DESIGNS%\%GLAYOUT_PATH%"
        
        :: Execute git commands
        git submodule add !GLAYOUT_REPOSITORY! !GLAYOUT_FOLDER!
        git submodule update --init --recursive

        echo [INFO] Selected repository !GLAYOUT_REPOSITORY! added and initialized successfully.
        echo [INFO] Please to install it, execute run_GL.sh inside the docker container.
        
        :: Return to the original directory
        popd
    )

)
