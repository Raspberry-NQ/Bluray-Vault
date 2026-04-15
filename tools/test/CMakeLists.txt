cmake_minimum_required(VERSION 3.20)

# Helper: create a test executable and register it with CTest
function(add_rs_test name)
    add_executable(${name} ${name}.c)
    target_link_libraries(${name} PRIVATE rs_code)
    add_test(NAME ${name} COMMAND ${name})
endfunction()

add_rs_test(test_gf_field)
add_rs_test(test_encode_decode)
add_rs_test(test_edge_cases)
