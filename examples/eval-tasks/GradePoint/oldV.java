public class oldV {
    // grade points for a score: 90 and above 4, 80s 3, 70s 2, 60s 1, below 60 0;
    // -1 for a score outside 0..100
    public static double snippet(int score) {
        int g = 0;
        if (score > 100) {
            g = -1;
        } else if (score >= 90) {
            g = 4;
        } else if (score >= 80) {
            g = 3;
        } else if (score >= 70) {
            g = 2;
        } else if (score >= 60) {
            g = 1;
        } else if (score >= 0) {
            g = 0;
        } else {
            g = -1;
        }
        return g;
    }
}
