public class fixedV {
    // reference fix: a year divisible by 400 is a leap year even though it is a century
    public static double snippet(int year) {
        int leap = 0;
        if (year % 4 == 0 && year % 100 != 0 || year % 400 == 0) {
            leap = 1;
        }
        return leap;
    }
}
