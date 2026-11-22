cmake_minimum_required(VERSION 3.20)
project(keyprobe_tip LANGUAGES CXX)

# The key probe (tools/keyprobe/README.md): a text service of its own, not part of ゆらぎ.
# It shares only the JSON reader with the product's TIP.
get_filename_component(YURAGI_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")

add_library(keyprobe_tip SHARED keyprobe_tip.cpp keyprobe_tip.def)
target_compile_features(keyprobe_tip PRIVATE cxx_std_17)
target_include_directories(keyprobe_tip PRIVATE "${YURAGI_ROOT}/src/tip")
target_compile_definitions(keyprobe_tip PRIVATE
  UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX WINVER=0x0A00 _WIN32_WINNT=0x0A00)
if(MSVC)
  target_compile_options(keyprobe_tip PRIVATE /utf-8 /W4)
endif()
target_link_libraries(keyprobe_tip PRIVATE ole32 oleaut32 uuid advapi32 user32)
set_target_properties(keyprobe_tip PROPERTIES
  PREFIX ""
  RUNTIME_OUTPUT_DIRECTORY "$<1:${CMAKE_CURRENT_SOURCE_DIR}/../out/tip>"
  LIBRARY_OUTPUT_DIRECTORY "$<1:${CMAKE_CURRENT_SOURCE_DIR}/../out/tip>"
)
