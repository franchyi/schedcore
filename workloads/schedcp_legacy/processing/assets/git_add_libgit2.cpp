#include <iostream>
#include <string>
#include <chrono>
#include <git2.h>

class GitAdder {
private:
    git_repository* repo = nullptr;
    git_index* index = nullptr;
    
public:
    ~GitAdder() {
        cleanup();
    }
    
    void cleanup() {
        if (index) {
            git_index_free(index);
            index = nullptr;
        }
        if (repo) {
            git_repository_free(repo);
            repo = nullptr;
        }
    }
    
    int performGitAdd(const std::string& repo_path) {
        int error = 0;
        
        // Initialize libgit2
        git_libgit2_init();
        
        // Open repository
        error = git_repository_open(&repo, repo_path.c_str());
        if (error < 0) {
            const git_error* e = git_error_last();
            std::cerr << "Error opening repository: " << (e ? e->message : "Unknown error") << std::endl;
            git_libgit2_shutdown();
            return error;
        }
        
        // Get repository index
        error = git_repository_index(&index, repo);
        if (error < 0) {
            const git_error* e = git_error_last();
            std::cerr << "Error getting index: " << (e ? e->message : "Unknown error") << std::endl;
            git_libgit2_shutdown();
            return error;
        }
        
        // Start timing
        auto start = std::chrono::high_resolution_clock::now();
        
        // Add all files to index (equivalent to git add .)
        error = git_index_add_all(index, nullptr, GIT_INDEX_ADD_DEFAULT, nullptr, nullptr);
        if (error < 0) {
            const git_error* e = git_error_last();
            std::cerr << "Error adding files: " << (e ? e->message : "Unknown error") << std::endl;
            git_libgit2_shutdown();
            return error;
        }
        
        // Write the index back to disk
        error = git_index_write(index);
        if (error < 0) {
            const git_error* e = git_error_last();
            std::cerr << "Error writing index: " << (e ? e->message : "Unknown error") << std::endl;
            git_libgit2_shutdown();
            return error;
        }
        
        // End timing
        auto end = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
        
        // Get statistics
        size_t entry_count = git_index_entrycount(index);
        
        std::cout << "Successfully added " << entry_count << " files to git index" << std::endl;
        std::cout << "Time taken: " << duration.count() << " ms" << std::endl;
        
        // Cleanup
        cleanup();
        git_libgit2_shutdown();
        
        return 0;
    }
};

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "Usage: " << argv[0] << " <repository_path>" << std::endl;
        return 1;
    }
    
    std::string repo_path = argv[1];
    
    GitAdder adder;
    int result = adder.performGitAdd(repo_path);
    
    return result < 0 ? 1 : 0;
}