cmake_minimum_required(VERSION 3.20)
project(yuragi_broker LANGUAGES CXX)

# The tag this build belongs to (DESIGN「置き場所」): the broker only runs when
# HKCU\Software\yuragi-ime\Tag names it. Release builds pass -DYURAGI_TAG=<tag>.
set(YURAGI_TAG "dev" CACHE STRING "the version tag compiled into the broker")

set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(broker_core STATIC broker_core.cpp broker_core.h support.cpp support.h)
if(MSVC)
  target_compile_options(broker_core PUBLIC /utf-8 /W4)
else()
  target_compile_options(broker_core PUBLIC -Wall -Wextra)
endif()

if(WIN32)
  add_executable(yuragi-broker WIN32 platform_win.cpp broker.rc)
  target_compile_definitions(yuragi-broker PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX WINVER=0x0A00 _WIN32_WINNT=0x0A00
    YURAGI_TAG="${YURAGI_TAG}")
  target_link_libraries(yuragi-broker PRIVATE broker_core
    advapi32 userenv shell32 user32 comctl32 ole32 uuid)
  if(MSVC)  # broker.rc carries the manifest; the linker must not add a second one
    target_link_options(yuragi-broker PRIVATE /MANIFEST:NO)
  endif()
  if(MINGW)  # wWinMain (MSVC finds it by itself); used to compile-check on Linux
    target_link_options(yuragi-broker PRIVATE -municode)
  endif()
  # The generator expression keeps multi-config generators from adding Release/.
  set_target_properties(yuragi-broker PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "$<1:${CMAKE_SOURCE_DIR}/../../dist>")
endif()

enable_testing()
# broker_core_test: the Broker with a fake platform; support_test: logs, notices, engine.json.
foreach(name broker_core support)
  add_executable(${name}_test tests/${name}_test.cpp)
  target_link_libraries(${name}_test PRIVATE broker_core)
  if(MSVC)
    target_compile_options(${name}_test PRIVATE /UNDEBUG)
  else()
    target_compile_options(${name}_test PRIVATE -UNDEBUG)
  endif()
  add_test(NAME ${name} COMMAND ${name}_test)
endforeach()
