cmake_minimum_required(VERSION 3.20)
project(rs_code
    VERSION 1.0.0
    LANGUAGES C
    DESCRIPTION "Cauchy Reed-Solomon Erasure Code Library"
)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# ---- Library ----
# Unified library (rs_code.h / rs_code.c)
add_library(rs_code STATIC
    rs_code.c
)
target_include_directories(rs_code PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# Shared library for Python ctypes binding
add_library(rs_code_shared SHARED
    rs_code.c
)
set_target_properties(rs_code_shared PROPERTIES
    OUTPUT_NAME "rs_code"
    POSITION_INDEPENDENT_CODE ON
)
target_include_directories(rs_code_shared PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# ---- Original source compatibility ----
# Build the original driver from the legacy source files
add_library(rs_code_legacy STATIC
    init_field.c
    get_msg.c
    encode.c
    lose_packets.c
    decode.c
    compare_msg.c
)
target_include_directories(rs_code_legacy PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)

# Original driver (legacy code)
add_executable(driver
    driver.c
)
target_link_libraries(driver PRIVATE rs_code_legacy)

# New driver (using the refactored library API)
add_executable(driver_lib
    driver_lib.c
)
target_link_libraries(driver_lib PRIVATE rs_code)

# ---- Tests ----
enable_testing()
add_subdirectory(test)
