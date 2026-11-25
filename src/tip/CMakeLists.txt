cmake_minimum_required(VERSION 3.20)
project(yuragi_tip LANGUAGES CXX)

# The tag this build belongs to (DESIGN「ブローカーを起動する条件」): an old or uninstalled
# DLL whose tag is not HKCU\Software\yuragi-ime\Tag never starts anything.
set(YURAGI_TAG "dev" CACHE STRING "the version tag compiled into the TIP")

find_package(Python3 REQUIRED COMPONENTS Interpreter)
get_filename_component(YURAGI_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(KEY_TABLE "${CMAKE_CURRENT_BINARY_DIR}/default_keymap.h")
file(GLOB KEYBOARD_FILES CONFIGURE_DEPENDS "${YURAGI_ROOT}/data/keyboards/*.json" "${YURAGI_ROOT}/data/nicola_*.json")
add_custom_command(OUTPUT "${KEY_TABLE}"
  COMMAND "${Python3_EXECUTABLE}" -m yuragi.ime.keymap "${KEY_TABLE}"
  WORKING_DIRECTORY "${YURAGI_ROOT}"
  DEPENDS "${YURAGI_ROOT}/yuragi/data/keymaps/ms-ime.json"
          "${YURAGI_ROOT}/yuragi/ime/keymap.py"
          "${YURAGI_ROOT}/yuragi/ime/commands.py"
          "${YURAGI_ROOT}/yuragi/chord/keys.py"
          ${KEYBOARD_FILES}
          "${YURAGI_ROOT}/yuragi/text.py"
  VERBATIM)
add_custom_target(tip_key_table DEPENDS "${KEY_TABLE}")

set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
if(WIN32)
  add_library(yuragi_tip SHARED
    yuragi_tip.cpp
    tip_json.h
    tip_logic.h
    tip_popup.h
    resource.h
    yuragi_tip.def
    yuragi_tip.rc
  )

  target_compile_features(yuragi_tip PRIVATE cxx_std_17)
  add_dependencies(yuragi_tip tip_key_table)
  target_include_directories(yuragi_tip PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  target_compile_definitions(yuragi_tip PRIVATE
    UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX WINVER=0x0A00 _WIN32_WINNT=0x0A00
    YURAGI_TAG="${YURAGI_TAG}")
  if(MSVC)
    target_compile_options(yuragi_tip PRIVATE /utf-8)
  endif()
  target_link_libraries(yuragi_tip PRIVATE ole32 oleaut32 uuid advapi32 user32 gdi32 userenv dwmapi)
  # 32-bit applications load the 32-bit build (DESIGN「32 ビットのアプリ」): beside the
  # 64-bit one in the same folder, so both find the broker next to them.
  if(CMAKE_SIZEOF_VOID_P EQUAL 4)
    set(TIP_NAME yuragi_tip32)
  else()
    set(TIP_NAME yuragi_tip)
  endif()
  # The generator expression keeps multi-config generators from adding Release/.
  set_target_properties(yuragi_tip PROPERTIES
    OUTPUT_NAME ${TIP_NAME}
    PREFIX ""
    RUNTIME_OUTPUT_DIRECTORY "$<1:${CMAKE_SOURCE_DIR}/../../dist>"
    LIBRARY_OUTPUT_DIRECTORY "$<1:${CMAKE_SOURCE_DIR}/../../dist>"
  )
endif()

# Also buildable on Linux: these executables have no Win32/TSF dependencies.
option(TIP_BUILD_TESTS "Build the TIP's JSON and decision checks (tip_json, tip_logic, keymap round trip)" ON)
if(TIP_BUILD_TESTS)
  enable_testing()
  add_executable(tip_json_test tests/tip_json_test.cpp tip_json.h)
  target_compile_features(tip_json_test PRIVATE cxx_std_17)
  # Assertions are the checks, including in Release builds.
  if(MSVC)
    target_compile_options(tip_json_test PRIVATE /UNDEBUG)
  else()
    target_compile_options(tip_json_test PRIVATE -UNDEBUG)
  endif()
  add_test(NAME tip_json COMMAND tip_json_test)

  # The TIP's decisions without TSF.
  add_executable(tip_logic_test tests/tip_logic_test.cpp tip_logic.h tip_json.h)
  add_dependencies(tip_logic_test tip_key_table)
  target_include_directories(tip_logic_test PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  target_compile_features(tip_logic_test PRIVATE cxx_std_17)
  if(MSVC)
    target_compile_options(tip_logic_test PRIVATE /UNDEBUG /utf-8)
  else()
    target_compile_options(tip_logic_test PRIVATE -UNDEBUG)
  endif()
  add_test(NAME tip_logic COMMAND tip_logic_test)
  add_test(NAME tip_keymap_roundtrip
    COMMAND "${Python3_EXECUTABLE}" -m tests.keymap_cases "$<TARGET_FILE:tip_logic_test>")
  set_tests_properties(tip_keymap_roundtrip PROPERTIES WORKING_DIRECTORY "${YURAGI_ROOT}")

  if(WIN32)
    # The connection to the broker: yuragi_tip.cpp itself, compiled into the test.
    add_executable(tip_link_test tests/tip_link_test.cpp)
    add_dependencies(tip_link_test tip_key_table)
    target_include_directories(tip_link_test PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
    target_compile_features(tip_link_test PRIVATE cxx_std_17)
    target_compile_definitions(tip_link_test PRIVATE
      UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX WINVER=0x0A00 _WIN32_WINNT=0x0A00
      YURAGI_TAG="${YURAGI_TAG}")
    if(MSVC)
      target_compile_options(tip_link_test PRIVATE /utf-8)
    endif()
    target_link_libraries(tip_link_test PRIVATE ole32 oleaut32 uuid advapi32 user32 gdi32 userenv dwmapi)
    add_test(NAME tip_link COMMAND tip_link_test)
  endif()

endif()
